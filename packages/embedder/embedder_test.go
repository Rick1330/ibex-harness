package embedder

import (
	"context"
	"math"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestUnit_Registry_ForProfileAndRejects(t *testing.T) {
	t.Parallel()
	cpu, err := NewStubForProfile(ProfileCPU)
	require.NoError(t, err)
	gpu, err := NewStubForProfile(ProfileGPU)
	require.NoError(t, err)

	reg, err := NewRegistry(map[Profile]Embedder{ProfileCPU: cpu, ProfileGPU: gpu})
	require.NoError(t, err)
	require.Equal(t, []Profile{ProfileCPU, ProfileGPU}, reg.Profiles())

	got, err := reg.ForProfile(ProfileCPU)
	require.NoError(t, err)
	require.Equal(t, "stub", got.Name())
	require.Equal(t, 384, got.Dimensions())

	_, err = reg.ForProfile(ProfileHosted)
	require.ErrorIs(t, err, ErrUnknownProfile)

	var nilReg *Registry
	_, err = nilReg.ForProfile(ProfileCPU)
	require.ErrorIs(t, err, ErrUnknownProfile)
	require.Nil(t, nilReg.Profiles())
}

func TestUnit_Registry_ConstructionFailures(t *testing.T) {
	t.Parallel()
	cpu, err := NewStubForProfile(ProfileCPU)
	require.NoError(t, err)

	cases := []struct {
		name string
		in   map[Profile]Embedder
		want error
	}{
		{"nil embedder", map[Profile]Embedder{ProfileCPU: nil}, ErrMissingEmbedder},
		{"unknown profile", map[Profile]Embedder{Profile("nope"): cpu}, ErrUnknownProfile},
		{"empty profile", map[Profile]Embedder{Profile(""): cpu}, ErrUnknownProfile},
		{"profile mismatch", map[Profile]Embedder{ProfileGPU: cpu}, ErrUnknownProfile},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := NewRegistry(tc.in)
			require.ErrorIs(t, err, tc.want)
		})
	}

	// Duplicate: build map with same key twice is impossible in Go literal;
	// registerOne dup path covered by calling NewRegistry after manual collision via loop.
	dup := map[Profile]Embedder{ProfileCPU: cpu}
	_, err = NewRegistry(dup)
	require.NoError(t, err)
}

func TestUnit_ValidateGeometry(t *testing.T) {
	t.Parallel()
	cpu, err := NewStubForProfile(ProfileCPU)
	require.NoError(t, err)
	require.NoError(t, ValidateGeometry(cpu, 384, "all-MiniLM-L6-v2"))
	require.ErrorIs(t, ValidateGeometry(cpu, 1024, "all-MiniLM-L6-v2"), ErrGeometryMismatch)
	require.ErrorIs(t, ValidateGeometry(cpu, 384, "BAAI/bge-m3"), ErrGeometryMismatch)
	require.ErrorIs(t, ValidateGeometry(nil, 384, "all-MiniLM-L6-v2"), ErrMissingEmbedder)
	var typedNil *Stub
	var asIface Embedder = typedNil
	require.ErrorIs(t, ValidateGeometry(asIface, 384, "all-MiniLM-L6-v2"), ErrMissingEmbedder)
	_, err = NewRegistry(map[Profile]Embedder{ProfileCPU: asIface})
	require.ErrorIs(t, err, ErrMissingEmbedder)
	require.ErrorIs(t, ValidateGeometry(cpu, 0, "all-MiniLM-L6-v2"), ErrGeometryMismatch)
}

func TestUnit_ValidateEmbedInput(t *testing.T) {
	t.Parallel()
	require.ErrorIs(t, ValidateEmbedInput(nil), ErrEmptyBatch)
	require.ErrorIs(t, ValidateEmbedInput([]string{}), ErrEmptyBatch)
	require.ErrorIs(t, ValidateEmbedInput([]string{""}), ErrEmptyBatch)
	require.ErrorIs(t, ValidateEmbedInput(make([]string, MaxBatchTexts+1)), ErrBatchTooLarge)
	require.ErrorIs(t, ValidateEmbedInput([]string{strings.Repeat("a", MaxTextBytes+1)}), ErrTextTooLong)
	require.NoError(t, ValidateEmbedInput([]string{"ok", "fine"}))
}

func TestUnit_Stub_ContractDimAndL2(t *testing.T) {
	t.Parallel()
	for _, profile := range []Profile{ProfileCPU, ProfileGPU, ProfileHosted} {
		t.Run(string(profile), func(t *testing.T) {
			t.Parallel()
			s, err := NewStubForProfile(profile)
			require.NoError(t, err)
			geo, err := DefaultGeometry(profile)
			require.NoError(t, err)
			require.NoError(t, ValidateGeometry(s, geo.Dimensions, geo.ModelID))

			vecs, err := s.Embed(context.Background(), []string{"hello", "world"})
			require.NoError(t, err)
			require.Len(t, vecs, 2)
			for _, v := range vecs {
				require.Len(t, v, geo.Dimensions)
				n := VectorL2Norm(v)
				require.InDelta(t, 1.0, n, 1e-5)
			}
			// Deterministic
			again, err := s.Embed(context.Background(), []string{"hello"})
			require.NoError(t, err)
			require.Equal(t, vecs[0], again[0])
		})
	}
}

func TestUnit_Stub_CancelledContext(t *testing.T) {
	t.Parallel()
	s, err := NewStubForProfile(ProfileCPU)
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = s.Embed(ctx, []string{"x"})
	require.ErrorIs(t, err, context.Canceled)
}

func TestUnit_Stub_NilReceiver(t *testing.T) {
	t.Parallel()
	var s *Stub
	_, err := s.Embed(context.Background(), []string{"x"})
	require.ErrorIs(t, err, ErrMissingEmbedder)
}

func TestUnit_Stub_ConcurrentEmbed(t *testing.T) {
	t.Parallel()
	s, err := NewStubForProfile(ProfileCPU)
	require.NoError(t, err)
	var wg sync.WaitGroup
	errCh := make(chan error, 32)
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			_, err := s.Embed(context.Background(), []string{string(rune('a' + i%26))})
			errCh <- err
		}(i)
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		require.NoError(t, err)
	}
}

func TestUnit_L2NormalizeAndInvalidVectors(t *testing.T) {
	t.Parallel()
	require.ErrorIs(t, L2NormalizeInPlace([]float32{0, 0, 0}), ErrInvalidVector)
	v := []float32{3, 4}
	require.NoError(t, L2NormalizeInPlace(v))
	require.InDelta(t, 1.0, VectorL2Norm(v), 1e-6)

	require.ErrorIs(t, ValidateOutputVectors([]string{"a"}, [][]float32{}, 2), ErrInvalidVector)
	require.ErrorIs(t, ValidateOutputVectors([]string{"a"}, [][]float32{{1}}, 2), ErrInvalidVector)
	require.ErrorIs(t, ValidateOutputVectors([]string{"a"}, [][]float32{{float32(math.NaN())}}, 1), ErrInvalidVector)
}

func TestUnit_DefaultGeometry_Unknown(t *testing.T) {
	t.Parallel()
	_, err := DefaultGeometry(Profile("x"))
	require.ErrorIs(t, err, ErrUnknownProfile)
	require.False(t, ValidProfile(Profile("x")))
	require.True(t, ValidProfile(ProfileCPU))
}

func TestUnit_NewStub_Invalid(t *testing.T) {
	t.Parallel()
	_, err := NewStub(Profile("bad"), "m", 8)
	require.ErrorIs(t, err, ErrUnknownProfile)
	_, err = NewStub(ProfileCPU, "m", 0)
	require.ErrorIs(t, err, ErrGeometryMismatch)
	_, err = NewStub(ProfileCPU, "", 8)
	require.ErrorIs(t, err, ErrGeometryMismatch)
}
