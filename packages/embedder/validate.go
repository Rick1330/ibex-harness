package embedder

import (
	"fmt"
	"math"
	"strings"
	"unicode/utf8"
)

// ValidateGeometry fails closed when the embedder's dim/model do not match expected config.
func ValidateGeometry(e Embedder, wantDim int, wantModel string) error {
	if embedderIsMissing(e) {
		return fmt.Errorf("%w: nil embedder", ErrMissingEmbedder)
	}
	wantModel = strings.TrimSpace(wantModel)
	if wantDim < 1 || wantModel == "" {
		return fmt.Errorf("%w: invalid expected geometry dim=%d model=%q", ErrGeometryMismatch, wantDim, wantModel)
	}
	if e.Dimensions() != wantDim {
		return fmt.Errorf("%w: dimensions got %d want %d", ErrGeometryMismatch, e.Dimensions(), wantDim)
	}
	if strings.TrimSpace(e.ModelID()) != wantModel {
		return fmt.Errorf("%w: model got %q want %q", ErrGeometryMismatch, e.ModelID(), wantModel)
	}
	return nil
}

func validateTextAt(index int, text string) error {
	if utf8.RuneCountInString(text) == 0 && len(text) == 0 {
		return fmt.Errorf("%w: empty text at index %d", ErrEmptyBatch, index)
	}
	if len(text) > MaxTextBytes {
		return fmt.Errorf("%w: index %d has %d bytes (max %d)", ErrTextTooLong, index, len(text), MaxTextBytes)
	}
	return nil
}

// ValidateEmbedInput rejects empty/oversized batches before calling a backend.
func ValidateEmbedInput(texts []string) error {
	if len(texts) == 0 {
		return ErrEmptyBatch
	}
	if len(texts) > MaxBatchTexts {
		return fmt.Errorf("%w: %d > %d", ErrBatchTooLarge, len(texts), MaxBatchTexts)
	}
	for i, t := range texts {
		if err := validateTextAt(i, t); err != nil {
			return err
		}
	}
	return nil
}

func vectorLenOK(v []float32, idx, dim int) error {
	if len(v) != dim {
		return fmt.Errorf("%w: index %d len %d want %d", ErrInvalidVector, idx, len(v), dim)
	}
	return nil
}

func vectorFiniteOK(v []float32, idx int) error {
	for j, x := range v {
		if math.IsNaN(float64(x)) || math.IsInf(float64(x), 0) {
			return fmt.Errorf("%w: non-finite at [%d][%d]", ErrInvalidVector, idx, j)
		}
	}
	return nil
}

// ValidateOutputVectors checks batch length, dim, and finite floats (not L2 — callers may assert separately).
func ValidateOutputVectors(texts []string, vectors [][]float32, dim int) error {
	if len(vectors) != len(texts) {
		return fmt.Errorf("%w: got %d vectors for %d texts", ErrInvalidVector, len(vectors), len(texts))
	}
	for i, v := range vectors {
		if err := vectorLenOK(v, i, dim); err != nil {
			return err
		}
		if err := vectorFiniteOK(v, i); err != nil {
			return err
		}
	}
	return nil
}

func invalidNormSum(sum float64) bool {
	return sum == 0 || math.IsNaN(sum) || math.IsInf(sum, 0)
}

func normSquaredSumOK(sum float64) error {
	if invalidNormSum(sum) {
		return fmt.Errorf("%w: cannot L2-normalize zero/non-finite vector", ErrInvalidVector)
	}
	return nil
}

// L2NormalizeInPlace scales v to unit length. Zero vectors become an error.
func L2NormalizeInPlace(v []float32) error {
	var sum float64
	for _, x := range v {
		sum += float64(x) * float64(x)
	}
	if err := normSquaredSumOK(sum); err != nil {
		return err
	}
	inv := float32(1 / math.Sqrt(sum))
	for i := range v {
		v[i] *= inv
	}
	return nil
}

// VectorL2Norm returns the Euclidean norm of v.
func VectorL2Norm(v []float32) float64 {
	var sum float64
	for _, x := range v {
		sum += float64(x) * float64(x)
	}
	return math.Sqrt(sum)
}
