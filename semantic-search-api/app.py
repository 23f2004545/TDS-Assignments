import os
import numpy as np

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from google import genai

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

app = Flask(__name__)
CORS(app)


def cosine_similarity(query_embedding, document_embeddings):

    query_embedding = np.array(query_embedding)
    query_embedding = query_embedding / np.linalg.norm(query_embedding)

    document_embeddings = np.array(document_embeddings)

    document_embeddings = (
        document_embeddings
        / np.linalg.norm(
            document_embeddings,
            axis=1,
            keepdims=True
        )
    )

    return document_embeddings @ query_embedding


@app.route("/")
def home():

    return jsonify({
        "status": "running"
    })


@app.route("/rank", methods=["POST"])
def rank():

    try:

        body = request.get_json()

        query = body["query"]
        candidates = body["candidates"]

        texts = [query] + candidates

        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=texts
        )

        embeddings = [
            embedding.values
            for embedding in response.embeddings
        ]

        query_embedding = embeddings[0]

        candidate_embeddings = embeddings[1:]

        similarities = cosine_similarity(
            query_embedding,
            candidate_embeddings
        )

        ranking = (
            np.argsort(-similarities)[:3]
            .astype(int)
            .tolist()
        )

        return jsonify({
            "ranking": ranking
        })

    except Exception as e:

        return jsonify({
            "ranking": [],
            "error": str(e)
        }), 500


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )