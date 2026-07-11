"""gRPC service implementation for EmbeddingService."""

import gc
import os
import sys
import time

import grpc
import torch
from FlagEmbedding import BGEM3FlagModel

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "grpc_generated"))

from grpc_generated import embedding_service_pb2 as embedding_pb2
from grpc_generated import embedding_service_pb2_grpc as embedding_pb2_grpc

from core.config import settings
from core.logger import logger

EMBEDDING_COLOR = "\033[38;5;147m"
RESET_COLOR = "\033[0m"

class EmbeddingServiceImplementation(embedding_pb2_grpc.EmbeddingServiceServicer):
    """Implementation of EmbeddingService gRPC service"""

    def __init__(self):
        """Initialize EmbeddingServiceImplementation."""
        self.models = {}
        self.default_model_id = "bge-m3"
        self.service_version = "0.1.0"

        # Create model registry
        self.model_registry = {
            "bge-m3": {
                "name": "BAAI/bge-m3",
                "dimensions": 1024,
                "supports_hybrid": True,
                "metadata": {
                    "description": "BGE M3 Embedding Model",
                    "provider": "BAAI",
                }
            },
            # Can add more models here
        }

        # Start loading models
        self._load_models()

    def _load_models(self):
        """Initialize models"""
        try:
            # Detect best device
            device = "cpu"
            logger.info(f"Selected device: {device}")
            logger.info(f"Loading BGE-M3 model...")

            # Configure model parameters
            use_fp16 = os.environ.get("USE_FP16", "true").lower() == "true" and device != "cpu"

            # If running on CPU, disable fp16 to avoid errors
            if device == "cpu" and use_fp16:
                use_fp16 = False
                logger.info("Disabled FP16 for CPU environment")

            # Use local model instead of downloading from Hugging Face
            model_path = os.environ.get("BGE_M3_MODEL_PATH", "/app/models/bge-m3")
            logger.info(f"Using local model path: {model_path}")

            model_params = {
                "model_name_or_path": model_path,
                "use_fp16": use_fp16,
                "device": device,
                "normalize_embeddings": True,
                "local_files_only": True,
                "query_max_length": settings.CHUNK_SIZE,
                "passage_max_length": settings.CHUNK_SIZE
            }

            # Load model
            logger.info(f"Loading model with parameters: device={device}, use_fp16={use_fp16}")
            try:
                self.models["bge-m3"] = BGEM3FlagModel(**model_params)
                logger.info("BGE-M3 model loaded successfully")
            except Exception as model_error:
                raise Exception(f"Failed to load model with alternative parameters: {str(model_error)}")

        except Exception as e:
            logger.error(f"Failed to load models: {str(e)}")

    def _pool_colbert_vectors(self, colbert_vecs_batch: list, pool_factor: int) -> list:
        """Apply token pooling to a batch of ColBERT matrices."""

        if pool_factor <= 1:
            return colbert_vecs_batch

        from pylate.models import ColBERT as PyLateColBERT

        tensors = [
            torch.nn.functional.normalize(torch.as_tensor(v, dtype=torch.float64), p=2, dim=1)
            for v in colbert_vecs_batch
        ]

        min_tokens = settings.CHUNK_SIZE // pool_factor
        pooled = PyLateColBERT.pool_embeddings_hierarchical(None, tensors, pool_factor=pool_factor)
        return [
            p.tolist() if t.shape[0] > min_tokens else t.tolist()
            for t, p in zip(tensors, pooled)
        ]

    def EmbedHybrid(self, request, context):
        """Implement EmbedHybrid RPC for a single query (EmbedQueryRequest.text)."""
        model_id = request.model if request.model else self.default_model_id

        try:
            start_time = time.time()
            query_text = (request.text or "").strip()
            if not query_text:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("text is required")
                return embedding_pb2.EmbedHybridResponse()

            model = self.models[model_id]
            outputs = model.encode(
                [query_text],
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=True,
            )

            colbert_vectors = self._pool_colbert_vectors(
                outputs["colbert_vecs"],
                settings.COLBERT_POOL_FACTOR,
            )

            dense = outputs["dense_vecs"][0]
            sparse = outputs["lexical_weights"][0]
            colbert = colbert_vectors[0]
            processing_time = time.time() - start_time

            logger.info("Embed hybrid query completed in %.2fs", processing_time)

            # EmbedHybridResponse is flat (not EmbedHybridDocumentsResponse)
            return embedding_pb2.EmbedHybridResponse(
                dense_vector=dense.tolist(),
                sparse_weights=dict(sparse),
                colbert_vectors=[
                    embedding_pb2.FloatVector(values=v) for v in colbert
                ],
                model=model_id,
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"Error in EmbedHybrid: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return embedding_pb2.EmbedHybridResponse()
        finally:
            torch.cuda.empty_cache()
            gc.collect()

    def EmbedHybridDocuments(self, request, context):
        """Implement EmbedHybridDocuments RPC method"""
        model_id = request.model if request.model else self.default_model_id

        try:
            start_time = time.time()

            # Call model embedding
            model = self.models[model_id]
            outputs = model.encode(
                request.texts,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=True
            )

            # Apply token pooling to ColBERT vectors
            colbert_vectors = self._pool_colbert_vectors(outputs['colbert_vecs'], settings.COLBERT_POOL_FACTOR)
            
            # Create hybrid embeddings
            hybrid_embeddings = [
                embedding_pb2.HybridEmbedding(
                    dense_vector=dense.tolist(),
                    sparse_weights=dict(sparse),
                    colbert_vectors=[embedding_pb2.FloatVector(values=v) for v in colbert],
                )
                for dense, sparse, colbert in zip(
                    outputs['dense_vecs'],
                    outputs['lexical_weights'],
                    colbert_vectors,
                )
            ]

            processing_time = time.time() - start_time

            logger.info(f"Embed hybrid documents completed in {processing_time:.2f}s")

            # Create and return response
            return embedding_pb2.EmbedHybridDocumentsResponse(
                embeddings=hybrid_embeddings,
                model=model_id,
                processing_time=processing_time
            )

        except Exception as e:
            logger.error(f"Error in EmbedHybridDocuments: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return embedding_pb2.EmbedHybridDocumentsResponse()
        finally:
            torch.cuda.empty_cache()
            gc.collect()