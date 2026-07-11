import os
import time
import logging
import grpc
from typing import Dict, Any, List
import numpy as np

# Import generated gRPC code
from app.grpc.embedding import embedding_service_pb2 as embedding_pb2
from app.grpc.embedding import embedding_service_pb2_grpc as embedding_pb2_grpc

# Import config
from app.core.logger import logger

class EmbeddingServiceClient:
    """Client class to interact with Embedding Service via gRPC."""

    def __init__(self, service_url: str, timeout: int = 30):
        """Initialize client.
        
        Args:
            service_url: URL of embedding service (host:port).
            timeout: Timeout for requests, default is 30 seconds.
        """
        self.service_url = service_url
        self.timeout = timeout
        self._channel = None
        self._stub = None
        
        # Thiết lập kết nối gRPC
        self._setup_connection()
    
    def _setup_connection(self):
        """Thiết lập kết nối gRPC và tạo stub."""
        try:
            # Thiết lập channel không bảo mật (insecure)
            self._channel = grpc.insecure_channel(
                self.service_url,
                options=[
                    ("grpc.max_receive_message_length", 1024 * 1024 * 1024),
                    ("grpc.max_send_message_length", 1024 * 1024 * 1024),
                ],
            )
            
            # Tạo stub để gọi các hàm của service
            self._stub = embedding_pb2_grpc.EmbeddingServiceStub(self._channel)
            
            # Kiểm tra kết nối
            self._check_connection()
            
            logger.info(f"Successfully connected to embedding service at {self.service_url}")
            
        except Exception as e:
            logger.error(f"Error connecting to embedding service: {str(e)}")
            self._stub = None
    
    def _check_connection(self):
        """Kiểm tra kết nối đến service bằng cách đợi channel ready."""
        try:
            grpc.channel_ready_future(self._channel).result(timeout=5)
            return True
        except grpc.FutureTimeoutError:
            logger.error("Timeout waiting for embedding service channel ready")
            return False
    
    def embed_hybrid(self, text: str, model: str = "bge-m3") -> Dict[str, Any]:
        """Tạo hybrid embedding cho câu truy vấn.
        
        Args:
            text: Câu truy vấn.
            model: ID của model cần sử dụng.
            
        Returns:
            Dict: Kết quả hybrid embedding bao gồm dense_vecs, colbert_vecs và lexical_weights.
        """
        if not self._stub:
            self._setup_connection()
            if not self._stub:
                raise ConnectionError("Không thể kết nối đến embedding service")
        
        try:
            # Tạo request
            request = embedding_pb2.EmbedQueryRequest(
                text=text,
                model=model
            )
            
            # Gọi RPC method
            start_time = time.time()
            response = self._stub.EmbedHybrid(request, timeout=self.timeout)
            process_time = time.time() - start_time
            
            # Chuyển đổi kết quả
            dense_vec = list(response.dense_vector)
            sparse_weights = dict(response.sparse_weights)
            colbert_vecs = [list(vec.values) for vec in response.colbert_vectors]
            
            # Log kết quả
            logger.debug(f"Created hybrid embedding for query (model={model}) in {process_time:.3f}s")
            
            # Return result as dict compatible with BGEM3
            return {
                "dense_vecs": [np.array(dense_vec)],
                "lexical_weights": [sparse_weights.items()],
                "colbert_vecs": [np.array([np.array(vec) for vec in colbert_vecs])]
            }
            
        except grpc.RpcError as e:
            raise e
    
    def embed_hybrid_documents(self, texts: List[str], model: str = "bge-m3") -> List[Dict[str, Any]]:
        """Create hybrid embeddings for a batch of documents.

        Args:
            texts: Documents to embed.
            model: Model ID to use.

        Returns:
            List of dicts with ``dense_vector``, ``sparse_weights``, ``colbert_vectors``.
        """
        if not self._stub:
            self._setup_connection()
            if not self._stub:
                raise ConnectionError("Unable to connect to embedding service")

        try:
            request = embedding_pb2.EmbedDocumentsRequest(texts=texts, model=model)
            start_time = time.time()
            response = self._stub.EmbedHybridDocuments(request, timeout=self.timeout)
            logger.debug(
                "Created hybrid embeddings for %d documents in %.3fs",
                len(texts),
                time.time() - start_time,
            )
            return [
                {
                    "dense_vector": list(emb.dense_vector),
                    "sparse_weights": dict(emb.sparse_weights),
                    "colbert_vectors": [list(vec.values) for vec in emb.colbert_vectors],
                }
                for emb in response.embeddings
            ]
        except grpc.RpcError as e:
            logger.error("gRPC EmbedHybridDocuments failed: %s", e)
            raise
    
    def close(self):
        """Close connection."""
        if self._channel:
            self._channel.close()
            self._channel = None
            self._stub = None
    
    def __del__(self):
        """Close connection when object is destroyed."""
        self.close()
