import React, { useState, useEffect, useRef } from 'react';
import { initializeApp } from 'firebase/app';
import { 
  getAuth, 
  signInAnonymously, 
  signInWithCustomToken,
  onAuthStateChanged 
} from 'firebase/auth';
import { 
  getFirestore, 
  collection, 
  doc, 
  setDoc, 
  onSnapshot, 
  query, 
  orderBy, 
  limit, 
  addDoc,
  serverTimestamp,
  updateDoc,
  deleteDoc
} from 'firebase/firestore';
import { 
  MessageSquare, 
  Brain, 
  Database, 
  Trash2, 
  Sparkles, 
  Activity,
  Cpu,
  RefreshCw,
  Send,
  Image as ImageIcon,
  X,
  Palette,
  Mic,
  MicOff,
  Volume2,
  Loader2,
  StopCircle
} from 'lucide-react';

// --- Configuration & Constants ---
const apiKey = ""; // Injected by environment
const TEXT_MODEL = "gemini-2.5-flash-preview-09-2025";
const IMAGE_MODEL = "imagen-4.0-generate-001";
const TTS_MODEL = "gemini-2.5-flash-preview-tts";

// --- Firebase Initialization ---
const firebaseConfig = JSON.parse(__firebase_config);
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const appId = typeof __app_id !== 'undefined' ? __app_id : 'default-app-id';

// --- Helper Functions ---

const convertToBase64 = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result);
    reader.onerror = error => reject(error);
  });
};

// PCM to WAV Converter for TTS
const pcmToWav = (pcmData, sampleRate = 24000) => {
  const buffer = new ArrayBuffer(44 + pcmData.length * 2);
  const view = new DataView(buffer);

  // RIFF identifier
  writeString(view, 0, 'RIFF');
  // RIFF chunk length
  view.setUint32(4, 36 + pcmData.length * 2, true);
  // RIFF type
  writeString(view, 8, 'WAVE');
  // fmt sub-chunk
  writeString(view, 12, 'fmt ');
  // fmt chunk length
  view.setUint32(16, 16, true);
  // format (1 = PCM)
  view.setUint16(20, 1, true);
  // channels (1 = mono)
  view.setUint16(22, 1, true);
  // sample rate
  view.setUint32(24, sampleRate, true);
  // byte rate
  view.setUint32(28, sampleRate * 2, true);
  // block align
  view.setUint16(32, 2, true);
  // bits per sample
  view.setUint16(34, 16, true);
  // data sub-chunk
  writeString(view, 36, 'data');
  // data chunk length
  view.setUint32(40, pcmData.length * 2, true);

  // Write PCM samples
  for (let i = 0; i < pcmData.length; i++) {
    view.setInt16(44 + i * 2, pcmData[i], true); // Little endian
  }

  return new Blob([view], { type: 'audio/wav' });
};

const writeString = (view, offset, string) => {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
};

// --- Helper Components ---

const MemoryCard = ({ fact, onDelete }) => (
  <div className="group flex items-start justify-between p-3 mb-2 bg-slate-800/50 border border-slate-700 rounded-lg hover:border-indigo-500/50 transition-all">
    <div className="flex items-start gap-3">
      <div className="mt-1">
        <Database className="w-4 h-4 text-indigo-400" />
      </div>
      <p className="text-sm text-slate-300 leading-snug">{fact.content}</p>
    </div>
    <button 
      onClick={() => onDelete(fact.id)}
      className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/20 rounded text-red-400 transition-all"
      title="Delete from Long Term Memory"
    >
      <Trash2 className="w-3.5 h-3.5" />
    </button>
  </div>
);

const ChatMessage = ({ message, onPlayAudio }) => {
  const isUser = message.role === 'user';
  const [isPlaying, setIsPlaying] = useState(false);

  const handlePlay = async () => {
    if (isPlaying) return;
    setIsPlaying(true);
    await onPlayAudio(message.content);
    setIsPlaying(false);
  };

  return (
    <div className={`flex w-full mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[85%] ${isUser ? 'flex-row-reverse' : 'flex-row'} gap-3`}>
        <div className={`
          w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0
          ${isUser ? 'bg-indigo-600' : 'bg-emerald-600'}
        `}>
          {isUser ? <span className="text-xs font-bold">YOU</span> : <Cpu className="w-4 h-4" />}
        </div>
        
        <div className={`
          p-4 rounded-2xl shadow-sm flex flex-col gap-3 relative group
          ${isUser 
            ? 'bg-indigo-600/20 text-indigo-100 rounded-tr-sm border border-indigo-500/30' 
            : 'bg-slate-800 text-slate-200 rounded-tl-sm border border-slate-700'}
        `}>
          {/* Image Attachment (User Upload) */}
          {message.attachment && (
            <div className="rounded-lg overflow-hidden border border-white/10 max-w-xs">
              <img src={message.attachment} alt="User upload" className="w-full h-auto object-cover" />
            </div>
          )}
          
          {/* Generated Image (Bot Creation) */}
          {message.generatedImage && (
            <div className="rounded-lg overflow-hidden border border-white/10 w-full">
              <img src={message.generatedImage} alt="AI Generated" className="w-full h-auto object-cover" />
              <div className="mt-2 text-xs text-slate-400 flex items-center gap-1">
                <Palette className="w-3 h-3" />
                Generated by Imagen 3
              </div>
            </div>
          )}

          {message.isThinking ? (
             <div className="flex gap-2 items-center text-emerald-400 text-sm animate-pulse">
               <Activity className="w-4 h-4" />
               <span>Processing...</span>
             </div>
          ) : (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
          )}

          {/* TTS Button (Only for Bot) */}
          {!isUser && !message.isThinking && message.content && (
            <button 
              onClick={handlePlay}
              disabled={isPlaying}
              className="absolute -bottom-6 left-0 p-1 text-slate-500 hover:text-emerald-400 transition-colors flex items-center gap-1"
              title="Read Aloud"
            >
              {isPlaying ? <Loader2 className="w-3 h-3 animate-spin" /> : <Volume2 className="w-3 h-3" />}
              <span className="text-[10px]">{isPlaying ? 'Speaking...' : 'Read'}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

// --- Main Application Component ---

export default function MemoryBot() {
  const [user, setUser] = useState(null);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]); 
  const [longTermFacts, setLongTermFacts] = useState([]);
  
  // Status States
  const [isProcessing, setIsProcessing] = useState(false);
  const [isLearning, setIsLearning] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  
  // Feature States
  const [selectedImage, setSelectedImage] = useState(null); 
  const [mode, setMode] = useState('chat'); // 'chat' or 'generate'
  
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);

  // 1. Authentication
  useEffect(() => {
    const initAuth = async () => {
      if (typeof __initial_auth_token !== 'undefined' && __initial_auth_token) {
        await signInWithCustomToken(auth, __initial_auth_token);
      } else {
        await signInAnonymously(auth);
      }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  // 2. Load Long-Term Memory
  useEffect(() => {
    if (!user) return;
    const factsRef = collection(db, 'artifacts', appId, 'users', user.uid, 'memory_facts');
    const q = query(factsRef); 
    const unsubscribe = onSnapshot(q, (snapshot) => {
      const facts = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      facts.sort((a, b) => (b.createdAt?.toMillis() || 0) - (a.createdAt?.toMillis() || 0));
      setLongTermFacts(facts);
    });
    return () => unsubscribe();
  }, [user]);

  // 3. Setup Speech Recognition
  useEffect(() => {
    if ('webkitSpeechRecognition' in window) {
      const recognition = new window.webkitSpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';
      
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInput(prev => prev + (prev ? ' ' : '') + transcript);
        setIsRecording(false);
      };
      
      recognition.onerror = () => setIsRecording(false);
      recognition.onend = () => setIsRecording(false);
      
      recognitionRef.current = recognition;
    }
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isProcessing, selectedImage]);

  // --- Handlers ---

  const handleImageSelect = async (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) return alert("Image too large. Limit 5MB.");
      const base64 = await convertToBase64(file);
      setSelectedImage(base64);
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      recognitionRef.current?.stop();
    } else {
      recognitionRef.current?.start();
      setIsRecording(true);
    }
  };

  const playTTS = async (text) => {
    try {
      // Clean text for speech (remove markdown asterisks, etc roughly)
      const cleanText = text.replace(/[*#]/g, '');
      
      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${TTS_MODEL}:generateContent?key=${apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contents: [{ parts: [{ text: cleanText }] }],
            generationConfig: {
              responseModalities: ["AUDIO"],
              speechConfig: {
                voiceConfig: { prebuiltVoiceConfig: { voiceName: "Fenrir" } }
              }
            }
          })
        }
      );

      const data = await response.json();
      const inlineData = data.candidates?.[0]?.content?.parts?.[0]?.inlineData;
      
      if (inlineData) {
        // Convert Base64 string to Uint8Array
        const binaryString = window.atob(inlineData.data);
        const len = binaryString.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        
        // PCM16 is returned, convert to WAV 16-bit 24kHz
        const wavBlob = pcmToWav(new Int16Array(bytes.buffer), 24000);
        const audioUrl = URL.createObjectURL(wavBlob);
        const audio = new Audio(audioUrl);
        audio.play();
      }
    } catch (err) {
      console.error("TTS Error:", err);
    }
  };

  const handleGenerateImage = async (prompt) => {
    const botId = Date.now();
    setMessages(prev => [...prev, { role: 'model', content: "Painting your masterpiece...", isThinking: true, id: botId }]);
    
    try {
      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${IMAGE_MODEL}:predict?key=${apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            // Enhanced prompt to enforce color and quality
            instances: [{ prompt: prompt + ", vibrant colors, high resolution, photorealistic, 8k" }],
            parameters: { 
              sampleCount: 1,
              aspectRatio: "1:1"
            }
          })
        }
      );
      
      const data = await response.json();
      const base64Image = data.predictions?.[0]?.bytesBase64Encoded;
      
      if (base64Image) {
        const imageUrl = `data:image/png;base64,${base64Image}`;
        setMessages(prev => prev.map(m => {
          if (m.id === botId) {
            return { 
              role: 'model', 
              content: `Here is the image for: "${prompt}"`, 
              generatedImage: imageUrl 
            };
          }
          return m;
        }));
        
        // Save to memory
        extractFactsFromInteraction(`User requested image: ${prompt}`, "I generated an image.");
      } else {
        throw new Error("No image returned");
      }
    } catch (err) {
      console.error(err);
      setMessages(prev => prev.map(m => {
        if (m.id === botId) return { role: 'model', content: "Sorry, I couldn't generate that image right now." };
        return m;
      }));
    } finally {
      setIsProcessing(false);
      setMode('chat');
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if ((!input.trim() && !selectedImage) || isProcessing) return;

    const userText = input;
    const userImg = selectedImage;
    
    // UI Reset
    setMessages(prev => [...prev, { role: 'user', content: userText, attachment: userImg }]);
    setInput('');
    setSelectedImage(null);
    setIsProcessing(true);

    // MODE CHECK: Image Generation
    if (mode === 'generate') {
      await handleGenerateImage(userText);
      return;
    }

    try {
      // Regular Chat Pipeline
      const memoryBlock = longTermFacts.map(f => `- ${f.content}`).join('\n');
      const systemInstruction = `
        You are an advanced Multimodal AI.
        
        === MEMORY ===
        ${memoryBlock.length > 0 ? memoryBlock : "No facts yet."}
        ==============

        Capabilities:
        1. VISION: Analyze uploaded images.
        2. MEMORY: Remember user facts.
        3. SPEECH: You can speak (user will see a button).
        
        Be concise and helpful.
      `;

      const chatHistoryForAPI = messages.map(m => {
        const parts = [];
        if (m.content) parts.push({ text: m.content });
        if (m.attachment) {
           const base64Data = m.attachment.split(',')[1]; 
           const mimeType = m.attachment.split(';')[0].split(':')[1];
           parts.push({ inlineData: { mimeType, data: base64Data } });
        }
        return {
          role: m.role === 'user' ? 'user' : 'model',
          parts: parts
        };
      });
      
      const currentParts = [];
      if (userText) currentParts.push({ text: userText });
      if (userImg) {
        const base64Data = userImg.split(',')[1];
        const mimeType = userImg.split(';')[0].split(':')[1];
        currentParts.push({ inlineData: { mimeType, data: base64Data } });
      }
      chatHistoryForAPI.push({ role: 'user', parts: currentParts });

      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${TEXT_MODEL}:generateContent?key=${apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contents: chatHistoryForAPI,
            systemInstruction: { parts: [{ text: systemInstruction }] }
          })
        }
      );

      const data = await response.json();
      const botResponseText = data.candidates?.[0]?.content?.parts?.[0]?.text || "System error.";
      
      setMessages(prev => [...prev, { role: 'model', content: botResponseText }]);

      const contextText = userImg ? `[Image Upload] ${userText}` : userText;
      extractFactsFromInteraction(contextText, botResponseText);

    } catch (error) {
      console.error("Chat Error:", error);
      setMessages(prev => [...prev, { role: 'model', content: "Connection error." }]);
    } finally {
      setIsProcessing(false);
    }
  };

  const extractFactsFromInteraction = async (userText, botText) => {
    setIsLearning(true);
    try {
      const extractionPrompt = `
        Extract NEW, PERMANENT facts about the user from this interaction for long-term memory.
        
        User: "${userText}"
        AI: "${botText}"
        
        Existing Memories: ${longTermFacts.map(f => f.content).join('; ')}
        
        Return ONLY the fact as a sentence. If no new facts, return "NO_FACTS".
        If multiple, use "|" separator.
      `;

      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${TEXT_MODEL}:generateContent?key=${apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ contents: [{ parts: [{ text: extractionPrompt }] }] })
        }
      );

      const data = await response.json();
      const result = data.candidates?.[0]?.content?.parts?.[0]?.text?.trim();

      if (result && result !== "NO_FACTS") {
        const newFacts = result.split('|').map(s => s.trim()).filter(s => s.length > 0 && s !== "NO_FACTS");
        for (const fact of newFacts) {
          const isDuplicate = longTermFacts.some(existing => existing.content.toLowerCase() === fact.toLowerCase());
          if (!isDuplicate && user) {
             await addDoc(collection(db, 'artifacts', appId, 'users', user.uid, 'memory_facts'), {
               content: fact,
               createdAt: serverTimestamp()
             });
          }
        }
      }
    } catch (err) {
      console.error("Memory Extraction Error:", err);
    } finally {
      setIsLearning(false);
    }
  };

  const deleteFact = async (factId) => {
    if (!user) return;
    await deleteDoc(doc(db, 'artifacts', appId, 'users', user.uid, 'memory_facts', factId));
  };

  const clearMemory = async () => {
     if (!user || !window.confirm("Wipe all memory?")) return;
     for (const fact of longTermFacts) {
       await deleteDoc(doc(db, 'artifacts', appId, 'users', user.uid, 'memory_facts', fact.id));
     }
  };

  const clearImage = () => {
    setSelectedImage(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // --- Render ---

  return (
    <div className="flex h-screen bg-slate-950 text-slate-200 font-sans overflow-hidden">
      
      {/* LEFT: Chat Interface */}
      <div className="flex-1 flex flex-col h-full border-r border-slate-800 relative">
        <div className="h-14 border-b border-slate-800 flex items-center px-6 bg-slate-900/50 backdrop-blur-md z-10 justify-between">
          <div className="flex items-center">
            <MessageSquare className="w-5 h-5 text-indigo-500 mr-2" />
            <h1 className="font-semibold text-slate-100">OmniBot v2.0</h1>
          </div>
          {isLearning && (
            <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-400/10 px-2 py-1 rounded-full animate-pulse">
              <Sparkles className="w-3 h-3" />
              <span>Memorizing...</span>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-500 opacity-60">
              <Brain className="w-16 h-16 mb-4 text-slate-600" />
              <p>I can See, Hear, Speak, and Draw.</p>
              <div className="flex gap-4 mt-4 text-xs">
                <span className="flex items-center gap-1"><Mic className="w-3 h-3"/> Voice Input</span>
                <span className="flex items-center gap-1"><Volume2 className="w-3 h-3"/> Text-to-Speech</span>
                <span className="flex items-center gap-1"><Palette className="w-3 h-3"/> Image Gen</span>
              </div>
            </div>
          ) : (
            messages.map((m, i) => (
              <ChatMessage key={i} message={m} onPlayAudio={playTTS} />
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className={`p-4 border-t border-slate-800 transition-colors ${mode === 'generate' ? 'bg-purple-900/20' : 'bg-slate-900'}`}>
          {selectedImage && (
            <div className="mb-2 flex items-center gap-2 bg-slate-800 w-fit px-3 py-2 rounded-lg border border-slate-700">
              <img src={selectedImage} alt="Preview" className="w-8 h-8 rounded object-cover border border-slate-600" />
              <span className="text-xs text-slate-300">Image attached</span>
              <button onClick={clearImage} className="ml-2 hover:bg-slate-700 rounded-full p-1 transition-colors">
                <X className="w-3 h-3 text-slate-400" />
              </button>
            </div>
          )}
          
          <form onSubmit={handleSendMessage} className="flex gap-2">
            <input 
              type="file" 
              accept="image/*" 
              className="hidden" 
              ref={fileInputRef}
              onChange={handleImageSelect}
            />
            
            {/* Tools Bar */}
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => {
                  setMode(prev => prev === 'generate' ? 'chat' : 'generate');
                  setSelectedImage(null); // Clear image if switching to gen mode
                }}
                className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all border ${mode === 'generate' ? 'bg-purple-600 border-purple-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-purple-400'}`}
                title={mode === 'generate' ? "Cancel Image Gen" : "Generate Image Mode"}
              >
                <Palette className="w-5 h-5" />
              </button>

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all bg-slate-800 border border-slate-700 text-slate-400 hover:text-indigo-400 ${mode === 'generate' ? 'opacity-50 cursor-not-allowed' : ''}`}
                title="Upload Image"
                disabled={isProcessing || mode === 'generate'}
              >
                <ImageIcon className="w-5 h-5" />
              </button>

              <button
                type="button"
                onClick={toggleRecording}
                className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all border ${isRecording ? 'bg-red-500/20 border-red-500 text-red-500 animate-pulse' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-red-400'}`}
                title="Voice Input"
                disabled={isProcessing}
              >
                {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
              </button>
            </div>

            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={mode === 'generate' ? "Describe image to generate..." : (isRecording ? "Listening..." : "Type a message...")}
              className={`flex-1 border text-white placeholder-slate-500 rounded-lg px-4 focus:outline-none focus:ring-2 transition-all ${mode === 'generate' ? 'bg-purple-900/10 border-purple-500/50 focus:ring-purple-500/50' : 'bg-slate-800 border-slate-700 focus:ring-indigo-500/50'}`}
              disabled={isProcessing}
            />
            
            <button 
              type="submit" 
              disabled={isProcessing || (!input.trim() && !selectedImage)}
              className={`text-white rounded-lg px-6 transition-colors flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed ${mode === 'generate' ? 'bg-purple-600 hover:bg-purple-700' : 'bg-indigo-600 hover:bg-indigo-700'}`}
            >
              {isProcessing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
            </button>
          </form>
        </div>
      </div>

      {/* RIGHT: Memory Visualization */}
      <div className="w-80 bg-slate-900/50 flex flex-col h-full border-l border-slate-800 shadow-xl">
        <div className="h-14 border-b border-slate-800 flex items-center justify-between px-4 bg-slate-900/80">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-emerald-400" />
            <h2 className="font-semibold text-sm tracking-wide text-slate-200">MEMORY</h2>
          </div>
          <div className="text-xs font-mono text-slate-500">
            {longTermFacts.length} FACTS
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 scrollbar-thin scrollbar-thumb-slate-700">
          {longTermFacts.length === 0 ? (
            <div className="text-center mt-10 p-4 border border-dashed border-slate-700 rounded-lg">
              <RefreshCw className="w-8 h-8 text-slate-600 mx-auto mb-2 opacity-50" />
              <p className="text-slate-500 text-sm">Memory Empty</p>
            </div>
          ) : (
            longTermFacts.map(fact => (
              <MemoryCard key={fact.id} fact={fact} onDelete={deleteFact} />
            ))
          )}
        </div>

        {longTermFacts.length > 0 && (
          <div className="p-4 border-t border-slate-800 bg-slate-900/30">
            <button 
              onClick={clearMemory}
              className="w-full flex items-center justify-center gap-2 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 py-2 rounded transition-colors"
            >
              <Trash2 className="w-3 h-3" />
              Clear Brain
            </button>
          </div>
        )}
      </div>

    </div>
  );
}