class AIProviderConfig:
    """Factory class for AI provider configurations"""

    @staticmethod
    def get_llm_config(provider, api_key, model_name, base_url=None):
        """Get LLM configuration based on provider"""
        config = {
            "openai_api_key": api_key,
            "model_name": model_name,
            "temperature": 0.2
        }

        if provider == "DeepSeek" and base_url:
            config["base_url"] = base_url
        elif provider == "OpenAI":
            # OpenAI specific configurations can be added here
            pass

        return config

    @staticmethod
    def get_default_model(provider):
        """
        Get default model for provider

        Args:
            provider (str): AI provider name (OpenAI, DeepSeek, etc.)

        Returns:
            str: Default model name for the provider
        """
        defaults = {
            "OpenAI": {
                "default": "gpt-3.5-turbo",
                "models": ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"]
            },
            "DeepSeek": {
                "default": "deepseek-chat",
                "models": ["deepseek-chat", "deepseek-reasoner"]
            }
        }

        provider_config = defaults.get(provider, defaults["OpenAI"])
        return provider_config["default"]

    @staticmethod
    def get_available_models(provider):
        """
        Get available models for provider

        Args:
            provider (str): AI provider name

        Returns:
            list: List of available models for the provider
        """
        defaults = {
            "OpenAI": {
                "default": "gpt-3.5-turbo",
                "models": ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"]
            },
            "DeepSeek": {
                "default": "deepseek-chat",
                "models": ["deepseek-chat", "deepseek-reasoner"]
            }
        }

        provider_config = defaults.get(provider, defaults["OpenAI"])
        return provider_config["models"]

    @staticmethod
    def is_valid_model(provider, model):
        """
        Check if model is valid for the given provider

        Args:
            provider (str): AI provider name
            model (str): Model name to validate

        Returns:
            bool: True if model is valid for provider
        """
        available_models = AIProviderConfig.get_available_models(provider)
        return model in available_models

    @staticmethod
    def validate_provider_config(provider, api_key, base_url=None):
        """Validate provider configuration"""
        if not api_key:
            return False, f"API key not configured for {provider}"

        if provider == "DeepSeek" and not base_url:
            return False, "Base URL required for DeepSeek provider"

        return True, None
