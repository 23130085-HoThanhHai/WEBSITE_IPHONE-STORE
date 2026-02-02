import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import os
import re


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(
    BASE_DIR,
    "ml_models",
    "phobert_sentiment"
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    use_fast=False
)

model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
model.to(device)
model.eval()

def predict_sentiment(text: str):
    if is_nonsense(text):
        return "neutral"

    inputs = tokenizer(
        text,
        truncation=True,
        padding=True,
        max_length=256,
        return_tensors="pt"
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.softmax(logits, dim=1)
        confidence, pred = torch.max(probs, dim=1)

    # 2. Nếu model không chắc
    if confidence.item() < 0.6:
        return "neutral"

    return "positive" if pred.item() == 1 else "negative"

# def predict_sentiment(text: str) -> int:
#     inputs = tokenizer(
#         text,
#         return_tensors="pt",
#         truncation=True,
#         padding=True,
#         max_length=256
#     )
#
#     inputs = {k: v.to(device) for k, v in inputs.items()}
#
#     with torch.no_grad():
#         outputs = model(**inputs)
#         pred = torch.argmax(outputs.logits, dim=1).item()
#
#     return pred
def is_nonsense(text: str) -> bool:
    text = text.lower().strip()

    # quá ngắn
    if len(text) < 5:
        return True

    # không có chữ cái (tiếng Việt + alphabet)
    if not re.search(r"[a-zA-Zàáạảãâầấậẩẫăằắặẳẵêềếệểễôồốộổỗơờớợởỡưừứựửữ]", text):
        return True

    # lặp từ quá nhiều (spam)
    words = text.split()
    if len(words) > 4 and len(set(words)) <= 2:
        return True

    return False

#test
if __name__ == "__main__":
    test_texts = [
        "Sản phẩm rất tốt, pin trâu, dùng mượt",
        "Máy quá tệ, pin yếu, rất thất vọng",
        "abc abc abc he he he",
        "cuộc sống hôm nay rất đẹp"
    ]

    for text in test_texts:
        label = predict_sentiment(text)
        print(text, "=>", label)

