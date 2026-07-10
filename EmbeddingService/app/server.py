"""Main gRPC server for EmbeddingService."""

import os
import signal
import sys
from concurrent import futures

import grpc

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "grpc_generated"))

from grpc_generated import embedding_service_pb2_grpc
from app.grpc_service import EmbeddingServiceImplementation
from core.config import settings
from core.logger import logger


class EmbeddingGrpcServer:
    """gRPC server for EmbeddingService."""

    def __init__(self):
        self.server = None
        self.running = False

    def setup_server(self):
        self.server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=settings.MAX_WORKERS),
            options=[
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.keepalive_permit_without_calls", True),
                ("grpc.http2.max_pings_without_data", 0),
                ("grpc.http2.min_time_between_pings_ms", 10000),
                ("grpc.http2.min_ping_interval_without_data_ms", 300000),
                ("grpc.max_send_message_length", 1024 * 1024 * 1024),
                ("grpc.max_receive_message_length", 1024 * 1024 * 1024),
            ],
        )

        embedding_service_pb2_grpc.add_EmbeddingServiceServicer_to_server(
            EmbeddingServiceImplementation(),
            self.server,
        )

        listen_addr = f"{settings.HOST}:{settings.PORT}"
        self.server.add_insecure_port(listen_addr)
        logger.info(f"Embedding gRPC server configured to listen on {listen_addr}")

    def start(self):
        if not self.server:
            self.setup_server()

        self.server.start()
        self.running = True
        logger.info(f"Embedding gRPC service started on {settings.HOST}:{settings.PORT}")

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            self.server.wait_for_termination()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            self.stop()

    def stop(self):
        if self.server and self.running:
            logger.info("Stopping Embedding gRPC server...")
            self.server.stop(grace=30)
            self.running = False
            logger.info("Embedding gRPC server stopped")

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()


def main():
    logger.info(f"Starting {settings.SERVICE_NAME}")

    server = EmbeddingGrpcServer()

    try:
        server.start()
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
