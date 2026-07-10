from pydantic import BaseModel, Field

class EmbedHybridResponse(BaseModel):
    """Hybrid embedding result."""

    dense_vector: list[float] = Field(..., description="Dense vector")
    sparse_weights: dict[str, float] = Field(..., description="Sparse vector")
    colbert_vectors: list[list[float]] = Field(..., description="ColBERT vectors")
