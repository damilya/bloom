import warnings

# langchain-openai structured output triggers a harmless pydantic serializer warning on every call
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
warnings.filterwarnings("ignore", message=".*allowed_objects.*")
