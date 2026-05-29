import kagglehub

# Download latest version
path = kagglehub.model_download("google/gemma-4/transformers/gemma-4-26b-a4b")

print("Path to model files:", path)