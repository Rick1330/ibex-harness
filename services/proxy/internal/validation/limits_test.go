package validation

import "testing"

func TestValidationLimits_saneDefaults(t *testing.T) {
	t.Parallel()

	if MaxRequestBodyBytes < 1 {
		t.Fatalf("MaxRequestBodyBytes: %d", MaxRequestBodyBytes)
	}
	if MaxProviderResponseBytes < MaxRequestBodyBytes {
		t.Fatalf("MaxProviderResponseBytes: %d", MaxProviderResponseBytes)
	}
	if MaxMessagesPerRequest < 1 {
		t.Fatalf("MaxMessagesPerRequest: %d", MaxMessagesPerRequest)
	}
	if MaxMessageContentBytes < 1 {
		t.Fatalf("MaxMessageContentBytes: %d", MaxMessageContentBytes)
	}
	if MaxModelNameLength < 1 {
		t.Fatalf("MaxModelNameLength: %d", MaxModelNameLength)
	}
	if MaxChatMaxTokens < 1 {
		t.Fatalf("MaxChatMaxTokens: %d", MaxChatMaxTokens)
	}
	if MinTemperature < 0 || MaxTemperature <= MinTemperature {
		t.Fatalf("temperature range: %f..%f", MinTemperature, MaxTemperature)
	}
}
