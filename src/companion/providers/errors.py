class LLMProviderError(Exception):
    retryable = False


class LLMConfigurationError(LLMProviderError):
    pass


class LLMTimeoutError(LLMProviderError):
    retryable = True


class LLMAuthenticationError(LLMProviderError):
    pass


class LLMRateLimitError(LLMProviderError):
    pass


class LLMTemporaryError(LLMProviderError):
    retryable = True


class LLMInvalidResponseError(LLMProviderError):
    pass
