from qdrant_client import QdrantClient, models
from app.grpc.embedding.embedding_client import EmbeddingServiceClient
import time
from core.config import settings
from core.logger import logger
import json
import uuid
class VectorStore:
    def __init__(self):
        self.qdrant_client = QdrantClient(
            host=settings.QDRANT_HOST,
            grpc_port=settings.QDRANT_GRPC_PORT,
            prefer_grpc=True
        )

        self.embedding_client = EmbeddingServiceClient(
            service_url=settings.EMBEDDING_SERVICE_URL,
            timeout=settings.EMBEDDING_SERVICE_TIMEOUT
        )
    
    def create_poi_collection(self, collection_name: str, embedding_size: int):
        self.qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=embedding_size,
                    distance=models.Distance.COSINE,
                    on_disk=True,
                    hnsw_config=models.HnswConfigDiff(
                        m=settings.QDRANT_HNSW_M,
                        ef_construct=settings.QDRANT_HNSW_EF_CONSTRUCT,
                        full_scan_threshold=settings.QDRANT_HNSW_FULL_SCAN_THRESHOLD,
                        on_disk=True,
                        inline_storage=True,
                    ),
                    quantization_config=models.TurboQuantization(
                        turbo=models.TurboQuantQuantizationConfig(
                            bits=models.TurboQuantBitSize.BITS1_5,
                            always_ram=True
                        )
                    ),
                ),
                "colbert": models.VectorParams(
                    size=embedding_size,
                    distance=models.Distance.COSINE,
                    multivector_config=models.MultiVectorConfig(
                        comparator=models.MultiVectorComparator.MAX_SIM
                    ),
                    hnsw_config=models.HnswConfigDiff(m=0),
                    on_disk=True,
                    datatype=models.Datatype.FLOAT16,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=True,
                    )
                ),
            },
            on_disk_payload=True,
            optimizers_config=models.OptimizersConfigDiff(
                default_segment_number=settings.QDRANT_DEFAULT_SEGMENT_NUMBER,
                max_segment_size=settings.QDRANT_MAX_SEGMENT_SIZE,
                indexing_threshold=settings.QDRANT_INDEXING_THRESHOLD,
            ),
        )
    
    def create_attribute_collection(self, collection_name: str, embedding_size: int):
        self.qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=embedding_size,
                )
            }
        )

    def upsert(self, collection_name: str, data: list[dict], batch_size: int = 100):
        # Create hybrid embeddings (dense, sparse, colbert) for current batch
        texts = data['text']
        metadatas = data['metadata']
        ids = [str(uuid.uuid4()) for _ in texts]

        for batch_idx in range(0, len(texts), batch_size):
            batch_texts = texts[batch_idx:batch_idx + batch_size]
            batch_metadatas = metadatas[batch_idx:batch_idx + batch_size]
            batch_ids = ids[batch_idx:batch_idx + batch_size]
        
            hybrid_embeddings = self.embedding_client.embed_hybrid(data)

            # Build separate lists for Batch upsert
            dense_vectors  = []
            colbert_vectors = []
            sparse_vectors = []
            payloads       = []

            for text, metadata, hybrid_embedding in zip(batch_texts, batch_metadatas, hybrid_embeddings):
                dense_vectors.append(hybrid_embedding['dense_vector'])
                colbert_vectors.append(hybrid_embedding['colbert_vectors'])
                sparse_vectors.append(self._create_sparse_vector(hybrid_embedding['sparse_weights']))
                payloads.append(json.loads(json.dumps(
                    {"text": text},
                    default=str,
                )))

        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=models.Batch(
                    ids=batch_ids,
                    vectors={
                        "dense":   dense_vectors,
                        "colbert": colbert_vectors,
                        "sparse":  sparse_vectors,
                    },
                    payloads=payloads
                )
            )
        except Exception as upsert_error:
            raise Exception(f"Error upserting data to collection {collection_name}: {upsert_error}")
    
    def bulk_upsert(self, collection_name: str, data: list[dict]):
        pass
    
    def poi_search(
        self, 
        collection_name: str, 
        query: str, 
        top_k: int, 
        prefetch_limit: int = 100
    ) -> list[dict]:
        try:
            query_embeddings = self.embedding_client.embed_hybrid(query)
            
            # Convert sparse weights to Qdrant format
            sparse_weights_dict = dict(query_embeddings['lexical_weights'][0])
            qdrant_sparse = self._create_sparse_vector(sparse_weights_dict)
            
            # Get dense vector
            dense_vector = query_embeddings['dense_vecs'][0]
            if hasattr(dense_vector, 'tolist'):
                logger.info(f"Need to convert dense vector to list")
                dense_vector = dense_vector.tolist()
            
            # Get colbert vectors
            colbert_vectors = query_embeddings['colbert_vecs'][0]
            if hasattr(colbert_vectors, 'tolist'):
                logger.info(f"Need to convert colbert vectors to list")
                colbert_vectors = colbert_vectors.tolist()
            
            # Set prefetch for hybrid search
            prefetch = [
                models.Prefetch(
                    query=qdrant_sparse,
                    using="sparse",
                    limit=prefetch_limit,
                ),
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=prefetch_limit,
                    params=models.SearchParams(
                        quantization=models.QuantizationSearchParams(
                            rescore=True,
                            oversampling=3.0
                        )
                    )
                )
            ]
            
            # Perform reranking with ColBERT
            query_params = {
                "collection_name": collection_name,
                "prefetch": prefetch,
                "query": colbert_vectors,
                "using": "colbert",
                "with_payload": True,
                "limit": top_k
            }
            
            start_time = time.time()
            results = self.qdrant_client.query_points(**query_params)
            end_time = time.time()
            logger.info(f"Time taken for hybrid search: {end_time - start_time} seconds")

            # distill_results = []
            # for point in results.points:
                
            #     metadata = {k: v for k, v in point.payload.items() if k != "text"}
            #     metadata["chunk_id"] = str(point.id) 

            #     distill_results.append({
            #         "content": point.payload.get("text", ""),
            #         "metadata": metadata,
            #         "score": point.score
            #     })
            # results = distill_results

            return results
        except Exception as e:
            raise Exception(f"Error performing hybrid search: {e}")
    
    def attribute_search(self, collection_name: str, query: str, top_k: int) -> list[dict]:
        pass