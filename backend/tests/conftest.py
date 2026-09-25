import os

# Unit tests use fake LLMs; keep their runs out of the LangSmith project (the real traces are what we demo).
# Set before app.config loads .env, and load_dotenv doesn't override existing variables.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
