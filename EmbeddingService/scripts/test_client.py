#!/usr/bin/env python3

import argparse
import os
import sys
import time
from pathlib import Path

import grpc

# Cho phép chạy cả khi không dùng uv (python scripts/test_client.py)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "grpc_generated"))

from grpc_generated import embedding_service_pb2 as pb
from grpc_generated import embedding_service_pb2_grpc as pbg

STATUS_NAME = {
    pb.StatusResponse.Status.UNKNOWN: "UNKNOWN",
    pb.StatusResponse.Status.READY: "READY",
    pb.StatusResponse.Status.LOADING: "LOADING",
    pb.StatusResponse.Status.ERROR: "ERROR",
}


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def call_status(stub: pbg.EmbeddingServiceStub, include_stats: bool = True) -> None:
    print_section("GetStatus")
    resp = stub.GetStatus(pb.StatusRequest(include_stats=include_stats))
    print(f"  status        : {STATUS_NAME.get(resp.status, resp.status)}")
    print(f"  version       : {resp.version}")
    print(f"  loaded_models : {list(resp.loaded_models)}")
    if resp.stats:
        print("  stats         :")
        for k, v in resp.stats.items():
            print(f"    - {k}: {v}")


def call_list_models(stub: pbg.EmbeddingServiceStub, include_details: bool = True) -> None:
    print_section("ListModels")
    resp = stub.ListModels(pb.ListModelsRequest(include_details=include_details))
    if not resp.models:
        print("  (không có model nào)")
        return
    for m in resp.models:
        print(f"  - id={m.id!r} name={m.name!r} loaded={m.loaded} "
              f"hybrid={m.supports_hybrid} dims={m.dimensions}")
        if m.metadata:
            for k, v in m.metadata.items():
                print(f"      {k}: {v}")


def call_embed_hybrid(stub: pbg.EmbeddingServiceStub, texts: list[str], model: str) -> None:
    print_section(f"EmbedHybrid ({len(texts)} text(s))")
    request = pb.EmbedDocumentsRequest(texts=texts, model=model)
    t0 = time.perf_counter()
    resp = stub.EmbedHybrid(request)
    elapsed = time.perf_counter() - t0

    print(f"  model            : {resp.model}")
    print(f"  processing_time  : {resp.processing_time:.4f}s (server)")
    print(f"  round-trip time  : {elapsed:.4f}s (client)")
    print(f"  num embeddings   : {len(resp.embeddings)}")

    for i, emb in enumerate(resp.embeddings):
        dense = list(emb.dense_vector)
        sparse = dict(emb.sparse_weights)
        colbert_shapes = [len(v.values) for v in emb.colbert_vectors]

        print(f"\n  [{i}] text={texts[i]!r}")
        print(f"      dense_dim     : {len(dense)}")
        if dense:
            preview = ", ".join(f"{x:.4f}" for x in dense[:5])
            print(f"      dense[:5]     : [{preview}, ...]")
        print(f"      sparse_terms  : {len(sparse)}")
        if sparse:
            top = sorted(sparse.items(), key=lambda kv: kv[1], reverse=True)[:5]
            preview = ", ".join(f"{k}:{v:.4f}" for k, v in top)
            print(f"      sparse top5   : {preview}")
        print(f"      colbert_vecs  : {len(colbert_shapes)} tokens "
              f"(first shapes: {colbert_shapes[:3]})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test client cho EmbeddingService gRPC")
    parser.add_argument("--addr", default=os.getenv("EMBEDDING_ADDR", "localhost:50051"),
                        help="Địa chỉ gRPC server (mặc định: localhost:50051)")
    parser.add_argument("--model", default="bge-m3", help="Model id gửi trong request")
    parser.add_argument("--rpc", choices=("all", "status", "models", "hybrid"),
                        default="all", help="RPC nào cần gọi (mặc định: all)")
    parser.add_argument("--texts", nargs="*",
                        default=["Hello world", "Học máy là một lĩnh vực thú vị"],
                        help="Các text để embed khi gọi EmbedHybrid")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="Timeout gRPC (giây) cho mỗi lời gọi")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print(f"Connecting to EmbeddingService at {args.addr} ...")
    channel = grpc.insecure_channel(args.addr)
    try:
        grpc.channel_ready_future(channel).result(timeout=args.timeout)
    except grpc.FutureTimeoutError:
        print(f"ERROR: không kết nối được tới server tại {args.addr} "
              f"trong {args.timeout}s.")
        return 2

    stub = pbg.EmbeddingServiceStub(channel)

    try:
        if args.rpc in ("all", "status"):
            call_status(stub)
        if args.rpc in ("all", "models"):
            call_list_models(stub)
        if args.rpc in ("all", "hybrid"):
            call_embed_hybrid(stub, args.texts, args.model)
    except grpc.RpcError as e:
        print(f"\nRPC ERROR: code={e.code().name} details={e.details()!r}")
        return 1
    finally:
        channel.close()

    print(f"\nDone. (addr={args.addr})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
