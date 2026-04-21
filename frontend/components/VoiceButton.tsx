"use client";
import { useState, useRef } from 'react';
import { Mic, MicOff, Loader2 } from 'lucide-react';

interface VoiceButtonProps {
    onTranscript: (text: string) => void;
    disabled?: boolean;
}

export default function VoiceButton({ onTranscript, disabled }: VoiceButtonProps) {
    const [state, setState] = useState<'idle' | 'recording' | 'transcribing'>('idle');
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            chunksRef.current = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunksRef.current.push(e.data);
            };

            mediaRecorder.onstop = async () => {
                stream.getTracks().forEach(t => t.stop());
                setState('transcribing');
                const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
                const formData = new FormData();
                formData.append('file', blob, 'recording.webm');
                try {
                    const res = await fetch('http://localhost:8000/api/transcribe', {
                        method: 'POST',
                        body: formData,
                    });
                    if (!res.ok) throw new Error(await res.text());
                    const { text } = await res.json();
                    onTranscript(text);
                } catch (err) {
                    console.error('Transcription error:', err);
                    alert('Transcription failed. Check that the backend is running and the Groq API key is valid.');
                } finally {
                    setState('idle');
                }
            };

            mediaRecorder.start();
            setState('recording');
        } catch {
            alert('Microphone access was denied or is unavailable.');
        }
    };

    const stopRecording = () => {
        mediaRecorderRef.current?.stop();
    };

    const handleClick = () => {
        if (state === 'idle') startRecording();
        else if (state === 'recording') stopRecording();
    };

    const title =
        state === 'recording' ? 'Stop recording' :
        state === 'transcribing' ? 'Transcribing…' :
        'Record voice input';

    return (
        <button
            type="button"
            onClick={handleClick}
            disabled={disabled || state === 'transcribing'}
            title={title}
            className={`inline-flex items-center justify-center w-8 h-8 rounded-full border focus:outline-none cursor-pointer disabled:opacity-50 transition-colors ${
                state === 'recording'
                    ? 'bg-red-500 border-red-600 text-white animate-pulse'
                    : 'bg-white border-gray-300 text-gray-500 hover:bg-gray-50 hover:text-indigo-600 hover:border-indigo-400'
            }`}
        >
            {state === 'transcribing' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
            ) : state === 'recording' ? (
                <MicOff className="w-4 h-4" />
            ) : (
                <Mic className="w-4 h-4" />
            )}
        </button>
    );
}
