import json
import os
import re
import argparse
import datetime
from collections import Counter

import torch
import torch.nn as nn
import torch.optim as optim

# ------------------------------
# Hyperparameters
# ------------------------------
MAX_VOCAB = 5000
HIDDEN_DIM = 128   
EMBED_DIM = 64

# ------------------------------
# Text preprocessing
# ------------------------------
def clean_text(text):
    text = text.lower()
    text = re.sub(r'[^a-z\s]', '', text)
    words = [w for w in text.split() if len(w) > 1]
    return words

# ------------------------------
# Autoencoder definition
# ------------------------------
class TextAutoencoder(nn.Module):
    def __init__(self, vocab_size):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(vocab_size, HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIM, EMBED_DIM)
        )
        self.decoder = nn.Sequential(
            nn.Linear(EMBED_DIM, HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIM, vocab_size),
            nn.Sigmoid()
        )

    def forward(self, x):
        embedding = self.encoder(x)
        reconstruction = self.decoder(embedding)
        return reconstruction, embedding

def count_parameters(model):
    return sum(p.numel() for p in model.parameters())

# ------------------------------
# Main training loop
# ------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", help="Input JSON file with papers")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=32)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    start_time = datetime.datetime.utcnow().isoformat() + "Z"

    print(f"Loading abstracts from {args.input_json}...")
    with open(args.input_json) as f:
        papers = json.load(f)

    abstracts = [p.get("abstract", "") for p in papers]
    tokenized = [clean_text(a) for a in abstracts]

    print(f"Found {len(abstracts)} abstracts")

    # ------------------------------
    # Build vocabulary
    # ------------------------------
    all_words = Counter(w for doc in tokenized for w in doc)
    total_words = sum(all_words.values())
    most_common = all_words.most_common(MAX_VOCAB - 1)

    vocab_to_idx = {w: i + 1 for i, (w, _) in enumerate(most_common)}
    vocab_to_idx["<UNK>"] = 0
    idx_to_vocab = {str(i): w for w, i in vocab_to_idx.items()}
    vocab_size = len(vocab_to_idx)

    print(f"Vocabulary size: {vocab_size}")

    # Save vocabulary
    with open(os.path.join(args.output_dir, "vocabulary.json"), "w") as f:
        json.dump({
            "vocab_to_idx": vocab_to_idx,
            "idx_to_vocab": idx_to_vocab,
            "vocab_size": vocab_size,
            "total_words": total_words
        }, f, indent=2)

    # ------------------------------
    # Initialize model
    # ------------------------------
    model = TextAutoencoder(vocab_size)
    total_params = count_parameters(model)

    print(f"Model architecture: {vocab_size} → {HIDDEN_DIM} → {EMBED_DIM} → {HIDDEN_DIM} → {vocab_size}")
    print(f"Total parameters: {total_params}")

    if total_params > 2_000_000:
        raise ValueError("Model exceeds 2,000,000 parameter limit!")

    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.BCELoss()

    # ------------------------------
    # Prepare Bag-of-Words tensors
    # ------------------------------
    data = []
    for doc in tokenized:
        vec = torch.zeros(vocab_size)
        for w in doc:
            idx = vocab_to_idx.get(w, 0)
            vec[idx] = 1.0
        data.append(vec)

    data = torch.stack(data)

    # ------------------------------
    # Training
    # ------------------------------
    print("Training autoencoder...")
    for epoch in range(args.epochs):
        total_loss = 0.0
        batches = 0

        for i in range(0, len(data), args.batch_size):
            batch = data[i:i + args.batch_size]

            optimizer.zero_grad()
            recon, _ = model(batch)
            loss = criterion(recon, batch)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            batches += 1

        avg_loss = total_loss / batches
        print(f"Epoch {epoch+1}/{args.epochs}, Loss: {avg_loss:.6f}")

    # ------------------------------
    # Generate embeddings + BCE reconstruction loss
    # ------------------------------
    embeddings_output = []
    bce_per_sample = nn.BCELoss(reduction='none')

    with torch.no_grad():
        recon, embed = model(data)
        losses = bce_per_sample(recon, data).mean(dim=1)

        for i, p in enumerate(papers):
            embeddings_output.append({
                "arxiv_id": p["arxiv_id"],
                "embedding": embed[i].tolist(),
                "reconstruction_loss": losses[i].item()
            })

    # ------------------------------
    # Save model
    # ------------------------------
    torch.save({
        "model_state_dict": model.state_dict(),
        "vocab_to_idx": vocab_to_idx,
        "model_config": {
            "vocab_size": vocab_size,
            "hidden_dim": HIDDEN_DIM,
            "embedding_dim": EMBED_DIM
        }
    }, os.path.join(args.output_dir, "model.pth"))

    # Save embeddings
    with open(os.path.join(args.output_dir, "embeddings.json"), "w") as f:
        json.dump(embeddings_output, f, indent=2)

    # Save training log
    end_time = datetime.datetime.utcnow().isoformat() + "Z"

    with open(os.path.join(args.output_dir, "training_log.json"), "w") as f:
        json.dump({
            "start_time": start_time,
            "end_time": end_time,
            "epochs": args.epochs,
            "final_loss": avg_loss,
            "total_parameters": total_params,
            "papers_processed": len(papers),
            "embedding_dimension": EMBED_DIM
        }, f, indent=2)

    print("Training complete.")

if __name__ == "__main__":
    main()