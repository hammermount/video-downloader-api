from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

@app.route('/api/info', methods=['POST'])
def fetch_info():
    try:
        data = request.get_json()
        url = data.get('url')

        if not url:
            return jsonify({'error': 'Missing URL'}), 400

        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'forcejson': True,
            'nocheckcertificate': True,
            'noplaylist': True,
            'extract_flat': False
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            formats = []
            for f in info.get('formats', []):
                height = f.get('height')
                ext = f.get('ext')
                if height in [480, 720, 1080] and ext in ['mp4', 'webm']:
                    formats.append({
                        'format_id': f.get('format_id'),
                        'resolution': height,
                        'ext': ext,
                        'filesize': f.get('filesize') or f.get('filesize_approx'),
                        'direct_url': f.get('url')  # This is the download/play URL
                    })

            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'formats': formats
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return jsonify({'message': 'Client-side video download API running ✅'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
