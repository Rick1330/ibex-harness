package validation

import "testing"

func TestValidationLimits_saneDefaults(t *testing.T) {
	t.Parallel()

	for _, tc := range []struct {
		name string
		got  int
	}{
		{"MaxRequestBodyBytes", MaxRequestBodyBytes},
		{"MaxProviderResponseBytes", MaxProviderResponseBytes},
		{"MaxMessagesPerRequest", MaxMessagesPerRequest},
		{"MaxMessageContentBytes", MaxMessageContentBytes},
		{"MaxModelNameLength", MaxModelNameLength},
		{"MaxChatMaxTokens", MaxChatMaxTokens},
	} {
		if tc.got < 1 {
			t.Fatalf("%s: %d", tc.name, tc.got)
		}
	}

	assertProviderResponseAboveRequest(t)
	assertTemperatureRange(t)
}

func assertProviderResponseAboveRequest(t *testing.T) {
	t.Helper()
	if MaxProviderResponseBytes < MaxRequestBodyBytes {
		t.Fatalf("MaxProviderResponseBytes: %d", MaxProviderResponseBytes)
	}
}

func assertTemperatureRange(t *testing.T) {
	t.Helper()
	if MinTemperature < 0 {
		t.Fatalf("MinTemperature: %f", MinTemperature)
	}
	if MaxTemperature <= MinTemperature {
		t.Fatalf("temperature range: %f..%f", MinTemperature, MaxTemperature)
	}
}
