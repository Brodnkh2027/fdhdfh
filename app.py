import streamlit as st
import whisper
import os
import asyncio
import edge_tts
from deep_translator import GoogleTranslator
from pydub import AudioSegment
import subprocess
import sys

# --- កំណត់ទំហំ Upload អតិបរមា (500MB) ---
st.config.set_option("server.maxUploadSize", 500)

# --- ០. កំណត់ផ្លូវ FFmpeg ---
# បញ្ជាក់៖ ប្រាកដថាអ្នកបានដំឡើង FFmpeg ក្នុងម៉ាស៊ីនរួចរាល់
ffmpeg_path = r"C:\ffmpeg\bin" 
if os.path.exists(ffmpeg_path):
    os.environ["PATH"] += os.pathsep + ffmpeg_path

# --- ១. មុខងារជំនួយ (Helper Functions) ---
async def generate_dubbing(segments, voice, rate):
    combined_audio = AudioSegment.empty()
    srt_output = ""
    
    def fmt(s):
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s%1)*1000):03}"

    my_bar = st.progress(0, text="AI កំពុងបកប្រែ និងផលិតសំឡេង...")
    total = len(segments)

    for i, seg in enumerate(segments):
        start_t, end_t, text_en = seg['start'], seg['end'], seg['text'].strip()
        if not text_en: continue

        # ២. បកប្រែជាភាសាខ្មែរ
        try:
            kh_text = GoogleTranslator(source='auto', target='km').translate(text_en)
        except:
            kh_text = text_en
        
        # ៣. រៀបចំទម្រង់ SRT
        srt_output += f"{i+1}\n{fmt(start_t)} --> {fmt(end_t)}\n{kh_text}\n\n"
        
        # ៤. AI Dubbing (Edge TTS)
        tmp = f"tmp_{i}.mp3"
        comm = edge_tts.Communicate(kh_text, voice, rate=rate)
        await comm.save(tmp)
        
        seg_audio = AudioSegment.from_mp3(tmp)
        silence = int(start_t * 1000) - len(combined_audio)
        if silence > 0: 
            combined_audio += AudioSegment.silent(duration=silence)
        
        combined_audio += seg_audio
        
        # លុប file បណ្ដោះអាសន្ន
        if os.path.exists(tmp):
            os.remove(tmp)
        
        my_bar.progress((i + 1) / total)
    
    return combined_audio, srt_output

# --- ២. កំណត់ UI និង Login ---
st.set_page_config(page_title="Speach Pro Studio", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'srt_data' not in st.session_state:
    st.session_state.srt_data = ""

# --- ផ្នែកកូនសោរ (Login) ---
if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>🔐 Speach Pro Studio v1.3</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login"):
            u = st.text_input("User", value="dara")
            k = st.text_input("Key", value="key-12345", type="password")
            if st.form_submit_button("ចូលប្រើប្រាស់ 🔓"):
                if u.strip() == "dara" and k.strip() == "key-12345":
                    st.session_state.logged_in = True
                    st.rerun()
                else: 
                    st.error("លេខកូដមិនត្រឹមត្រូវ!")

# --- ផ្នែកកម្មវិធីចម្បង ---
else:
    st.title("🎙️ Expert Dubbing Studio")
    
    with st.sidebar:
        st.header("⚙️ ការកំណត់")
        voice = st.selectbox("សំឡេង AI:", ["km-KH-PisethNeural", "km-KH-SreymomNeural"])
        speed = st.slider("ល្បឿន:", -50, 50, 0)
        if st.button("🔄 Make New (Clear Project)"):
            st.session_state.srt_data = ""
            st.rerun()
        if st.button("Logout 🚪"):
            st.session_state.logged_in = False
            st.rerun()

    # ១. បង្ហោះវីដេអូ (កំណត់ត្រឹម ៥០០មេកាបៃ)
    v_file = st.file_uploader("បង្ហោះវីដេអូ (MP4, MOV, AVI, MKV) - Max 500MB", type=["mp4","mov","avi","mkv"])

    if v_file:
        if v_file.size > 500 * 1024 * 1024:
            st.error("ឯកសារធំជាង ៥០០មេកាបៃ!")
        else:
            st.video(v_file)
            if st.button("🚀 ចាប់ផ្ដើមផលិត SRT & Dubbing"):
                with st.spinner("កំពុងដំណើរការ..."):
                    # រក្សាទុក file វីដេអូ
                    with open("in.mp4", "wb") as f: 
                        f.write(v_file.getbuffer())
                    
                    # ប្រើ Whisper ដើម្បីបំប្លែងសំឡេងជាអត្ថបទ
                    model = whisper.load_model("base")
                    res = model.transcribe("in.mp4")
                    
                    # ផលិត Dubbing និង SRT
                    audio, srt = asyncio.run(generate_dubbing(res['segments'], voice, f"{speed:+d}%"))
                    st.session_state.srt_data = srt
                    audio.export("out.mp3", format="mp3")
                    
                    if os.path.exists("in.mp4"):
                        os.remove("in.mp4")

    # បង្ហាញលទ្ធផល
    if st.session_state.srt_data:
        st.divider()
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("📄 Srt File (Khmer)")
            st.text_area("កែសម្រួល SRT:", value=st.session_state.srt_data, height=300)
            st.download_button("📥 ទាញយក .SRT", st.session_state.srt_data, "sub.srt")
        
        with col_r:
            st.subheader("🔊 AI Dubbed Audio (MP3)")
            if os.path.exists("out.mp3"):
                st.audio("out.mp3")
                with open("out.mp3", "rb") as a:
                    st.download_button("📥 ទាញយក .MP3", a, "dub.mp3")
