import numpy as np
from sentence_transformers import SentenceTransformer


def main() -> None:
    # 第一次运行时会自动下载中文Embedding模型
    model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

    #测试句子
    texts = [
        "我喜欢吃葡挞",
        "我喜欢的食物是什么",
        "图书馆应该怎么走",
    ]

    # normalize_embeddings=True表示将向量归一化
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
    )

    #用第二个句子作为查询
    query_embedding = embeddings[1]

    for index, text in enumerate(texts):
        similarity = float(
            np.dot(query_embedding, embeddings[index])
        )

        print(f"{text}：{similarity:.4f}")


if __name__ == "__main__":
    main()