import wave
import math
import struct

def generate_alert_sound():
    sample_rate = 44100
    duration = 1.0
    frequency = 800
    
    num_samples = int(sample_rate * duration)
    
    with wave.open('static/alert.wav', 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        for i in range(num_samples):
            value = int(32767 * 0.5 * math.sin(2 * math.pi * frequency * i / sample_rate))
            
            envelope = 1.0
            if i < sample_rate * 0.1:
                envelope = i / (sample_rate * 0.1)
            elif i > sample_rate * 0.9:
                envelope = (num_samples - i) / (sample_rate * 0.1)
            
            value = int(value * envelope)
            
            wav_file.writeframes(struct.pack('<h', value))
    
    print("Alert sound generated: static/alert.wav")

if __name__ == '__main__':
    generate_alert_sound()
