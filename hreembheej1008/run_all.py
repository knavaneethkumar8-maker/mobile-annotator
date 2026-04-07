import os
import torch
import numpy as np
import soundfile as sf
import librosa
from tqdm import tqdm
import torch.nn as nn

SR = 16000
WIN_MS = 54
WIN = int(SR * WIN_MS / 1000)
CONTEXT = 2
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv1d(5,32,5,padding=2),
            nn.ReLU(),
            nn.Conv1d(32,64,5,padding=2),
            nn.ReLU()
        )
        self.lstm = nn.LSTM(64,128,2,batch_first=True,bidirectional=True)
        self.attn = nn.Linear(256,1)
        self.fc = nn.Sequential(
            nn.Linear(256,128),
            nn.ReLU(),
            nn.Linear(128,2)
        )

    def forward(self,x):
        x=self.cnn(x)
        x=x.permute(0,2,1)
        out,_=self.lstm(x)
        w=torch.softmax(self.attn(out),dim=1)
        x=(out*w).sum(dim=1)
        return self.fc(x)

def load_audio(p):
    wav, sr = sf.read(p)
    if wav.ndim>1:
        wav=wav.mean(axis=1)
    if sr!=SR:
        wav = librosa.resample(wav, orig_sr=sr, target_sr=SR)
    wav = wav.astype(np.float32)
    wav /= (np.max(np.abs(wav))+1e-6)
    return wav

def write_textgrid(path, intervals, total_dur):
    with open(path, "w", encoding="utf-8") as f:
        f.write('File type = "ooTextFile"\n')
        f.write('Object class = "TextGrid"\n\n')
        f.write(f"xmin = 0\nxmax = {total_dur}\n")
        f.write("tiers? <exists>\nsize = 1\nitem []:\n")
        f.write('    item [1]:\n')
        f.write('        class = "IntervalTier"\n')
        f.write('        name = "dham_align"\n')
        f.write(f"        xmin = 0\nxmax = {total_dur}\n")
        f.write(f"        intervals: size = {len(intervals)}\n")

        for i,(xmin,xmax,text) in enumerate(intervals,1):
            f.write(f"        intervals [{i}]:\n")
            f.write(f"            xmin = {xmin}\n")
            f.write(f"            xmax = {xmax}\n")
            f.write(f'            text = "{text}"\n')

def process_file(wav_path, model):

    wav = load_audio(wav_path)
    total_dur = len(wav)/SR

    windows = []
    for i in range(0, len(wav)-WIN, WIN):
        frames=[]
        for c in range(-CONTEXT, CONTEXT+1):
            s = i + c*WIN
            if 0 <= s and s+WIN <= len(wav):
                frames.append(wav[s:s+WIN])
            else:
                frames.append(np.zeros(WIN))
        windows.append(np.stack(frames))

    windows = np.array(windows, dtype=np.float32)

    probs = []
    with torch.no_grad():
        for i in range(0, len(windows), 256):
            batch = torch.tensor(windows[i:i+256]).to(DEVICE)
            p = torch.softmax(model(batch), dim=1)[:,1].cpu().numpy()
            probs.extend(p)

    probs = np.array(probs)

    N = 1008
    step = len(probs)/N
    labels = [""] * len(probs)

    for i in range(N):
        start = int(i*step)
        end = int((i+1)*step)
        if end <= start: continue

        m_idx = max(range(start, end), key=lambda j: probs[j])

        labels[m_idx] = "म"
        if m_idx-1 >= start: labels[m_idx-1] = "अ"
        if m_idx-2 >= start: labels[m_idx-2] = "ह"

    intervals = []
    for i, lab in enumerate(labels):
        t1 = i*WIN/SR
        t2 = (i+1)*WIN/SR
        intervals.append((t1,t2,lab))

    tg_path = wav_path.replace(".wav", ".TextGrid")
    write_textgrid(tg_path, intervals, total_dur)

    print("✅ Done:", tg_path)


def run_all():

    model = Model().to(DEVICE)
    model.load_state_dict(torch.load("nasal_model.pt", map_location=DEVICE))
    model.eval()

    for file in os.listdir("."):
        if file.endswith(".wav") and "4x" in file:
            process_file(file, model)


if __name__ == "__main__":
    run_all()