from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import os, uuid, json, subprocess, shutil
from datetime import datetime
from gtts import gTTS
from tashkeel_helper import add_tashkeel_to_text

app = Flask(__name__)
UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
TTS_HISTORY = "/tmp/tts_history.json"

VOICES = {
    "ar-EG-SalmaNeural": "أنثوي - مصري",
    "ar-EG-ShakirNeural": "ذكوري - مصري",
    "ar-SA-ZariyahNeural": "أنثوي - سعودي",
    "ar-SA-HamedNeural": "ذكوري - سعودي",
    "ar-MA-MounaNeural": "أنثوي - مغربي",
    "ar-MA-JamalNeural": "ذكوري - مغربي",
    "ar-DZ-AminaNeural": "أنثوي - جزائري",
    "ar-DZ-IsmaelNeural": "ذكوري - جزائري",
    "ar-AE-FatimaNeural": "أنثوي - إماراتي",
    "ar-AE-HamdanNeural": "ذكوري - إماراتي",
    "ar-IQ-RanaNeural": "أنثوي - عراقي",
    "ar-IQ-BasselNeural": "ذكوري - عراقي",
    "ar-LY-ImanNeural": "أنثوي - ليبي",
    "ar-LY-OmarNeural": "ذكوري - ليبي",
    "ar-TN-ReemNeural": "أنثوي - تونسي",
    "ar-TN-HediNeural": "ذكوري - تونسي",
}

PITCH_MAP = {
    "normal": "+0Hz", "child": "+50Hz", "elder": "-40Hz",
    "deep": "-25Hz", "soft": "+25Hz", "whisper": "-10Hz",
    "sad": "-15Hz", "happy": "+20Hz", "angry": "-5Hz", "mysterious": "-20Hz",
}


import numpy as np
import soundfile as sf
import io

def pitch_shift_audio(input_path, output_path, semitones=-5):
    """خفض النغمة لتحويل الصوت الأنثوي إلى ذكوري"""
    try:
        # قراءة الصوت
        data, samplerate = sf.read(input_path)
        
        # تغيير النغمة بتغيير معدل العينة
        factor = 2 ** (semitones / 12.0)
        new_samplerate = int(samplerate * factor)
        
        # حفظ بمعدل العينة الجديد (يغير النغمة والسرعة)
        sf.write(output_path, data, new_samplerate)
        
        # استخدام gTTS لجعل الصوت بالسرعة الصحيحة
        # (اختياري: نتركه كما هو)
        print("--> Pitch shifted OK")
        return True
    except Exception as e:
        print(f"--> Pitch shift failed: {e}")
        return False

def gen_audio(text, voice, output_path, rate="+0%", pitch="+0Hz"):
    """توليد الصوت باستخدام gTTS (يعمل بدون websockets)"""
    print(f"--> gTTS: generating audio...")
    try:
        # gTTS يدعم العربية
        slow = (rate == "-30%")
        tts = gTTS(text=text, lang='ar', slow=slow)
        tts.save(output_path)
        print(f"--> Audio OK")
        return True
    except Exception as e:
        print(f"--> Audio failed: {str(e)[:100]}")
        raise

def add_music_audio(aud, mus, out):
    subprocess.run(["ffmpeg","-y","-i",aud,"-i",mus,"-filter_complex","[0:a]volume=1.0[a1];[1:a]volume=0.20[a2];[a1][a2]amix=inputs=2:duration=first[aout]","-map","[aout]","-c:a","libmp3lame","-b:a","192k",out], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def save_phone(path, name):
    """على Render، لا يوجد sdcard. نرجع الاسم فقط"""
    return name

def load_hist():
    if os.path.exists(TTS_HISTORY):
        try:
            with open(TTS_HISTORY) as f: return json.load(f)
        except: return []
    return []

def save_hist(h):
    with open(TTS_HISTORY, 'w') as f: json.dump(h[:10], f, ensure_ascii=False)


@app.route('/health')
def health():
    return 'OK', 200

@app.route('/')
def home(): return render_template('tts.html', voices=VOICES)

@app.route('/upload_music', methods=['POST'])
def up():
    f = request.files.get('file')
    if not f: return jsonify({'error':'No file'}), 400
    n = f"uploaded_{uuid.uuid4().hex[:8]}.mp3"
    f.save(os.path.join(UPLOAD_FOLDER, n))
    return jsonify({'success': True, 'file': n}), 200

@app.route('/tashkeel', methods=['POST'])
def tash():
    try:
        return jsonify({'tashkeel': add_tashkeel_to_text(request.json.get('text',''))}), 200
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/tts_generate', methods=['POST'])
def tts_gen():
    d = request.json
    text = d.get('text','').strip()
    if not text: return jsonify({'error':'أدخل النص'}), 400
    voice = d.get('voice','ar-EG-SalmaNeural')
    rate = d.get('rate','+0%')
    effect = d.get('voice_effect','normal')
    pitch = PITCH_MAP.get(effect, "+0Hz")
    fn = f"tts_{uuid.uuid4().hex[:8]}.mp3"
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), fn)
    try:
        print(f"--> TTS: voice={voice}, effect={effect}, pitch={pitch}")
        gen_audio(text, voice, out, rate, pitch)
        mt = d.get('music_type','none')
        um = d.get('uploaded_music','')
        mp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "background_music.mp3") if mt == 'app' else (os.path.join(UPLOAD_FOLDER, um) if mt == 'uploaded' and um else None)
        if mp and os.path.exists(mp):
            mixed = out.replace('.mp3','_m.mp3')
            add_music_audio(out, mp, mixed)
            os.replace(mixed, out)
        save_phone(out, fn)
        h = load_hist()
        h.insert(0, {'file': fn, 'text': text[:100], 'voice': VOICES.get(voice, voice), 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')})
        save_hist(h)
        return jsonify({'success': True, 'file': fn}), 200
    except Exception as e:
        print(f"--> Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/history', methods=['GET'])
def hist():
    return jsonify({'history': load_hist()}), 200

@app.route('/history/delete/<filename>', methods=['DELETE'])
def del_h(filename):
    h = load_hist()
    h = [x for x in h if x['file'] != filename]
    save_hist(h)
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(p): os.remove(p)
    return jsonify({'success': True}), 200

@app.route('/history/clear', methods=['DELETE'])
def clr_h():
    h = load_hist()
    for x in h:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), x['file'])
        if os.path.exists(p): os.remove(p)
    save_hist([])
    return jsonify({'success': True}), 200

@app.route('/download/<filename>')
def dl(filename):
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), filename, as_attachment=True)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
