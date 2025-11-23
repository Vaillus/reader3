import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import google.generativeai as genai
from dotenv import load_dotenv

# Load .env file from project root (3 levels up from this file)
env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(env_path)

class ChatService:
    """Service for handling LLM chat interactions with chapter context."""
    
    def __init__(self):
        """Initialize the Gemini model."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        
        genai.configure(api_key=api_key)
        # Use Gemini 1.5 Pro (more stable and widely available)
        # Alternative: 'gemini-2.0-flash-exp' for faster responses
        self.model = genai.GenerativeModel('gemini-3-pro-preview')
    
    def build_system_prompt(
        self,
        chapter_title: str,
        chapter_text: str,
        current_notes: str,
        book_title: Optional[str] = None
    ) -> str:
        """Build the system prompt with chapter context and current notes."""
        # Truncate chapter text if too long (keep first 8000 chars to leave room for notes and conversation)
        truncated_chapter = chapter_text[:8000]
        if len(chapter_text) > 8000:
            truncated_chapter += "\n\n[... chapter continues ...]"
        
        prompt = f"""Tu es un assistant de lecture intelligent. L'utilisateur lit le chapitre '{chapter_title}'"""
        
        if book_title:
            prompt += f" du livre '{book_title}'"
        
        prompt += """.

Voici le contenu du chapitre :

---
{truncated_chapter}
---

Voici les notes que l'utilisateur a prises pour l'instant :

---
{current_notes if current_notes.strip() else "(Aucune note pour l'instant)"}
---

Tu peux :
- Répondre aux questions sur le chapitre
- Analyser le contenu
- Aider à comprendre les concepts
- Suggérer des améliorations aux notes

IMPORTANT : Si l'utilisateur te demande d'ajouter ou de modifier ses notes, tu dois répondre avec un format spécial :
- Pour modifier les notes, termine ta réponse par une ligne commençant par "NOTE_UPDATE:" suivie du nouveau contenu complet des notes (en Markdown).
- Sinon, réponds normalement.

Exemple de réponse avec mise à jour de notes :
"Voici un résumé du chapitre...

NOTE_UPDATE:
# Notes du chapitre

## Points clés
- Point 1
- Point 2

## Réflexions
..."
"""
        return prompt
    
    def send_message(
        self,
        user_message: str,
        chapter_title: str,
        chapter_text: str,
        current_notes: str,
        conversation_history: List[Dict[str, str]],
        book_title: Optional[str] = None,
        quoted_text: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Send a message to the LLM and get response.
        
        Args:
            user_message: The user's message
            chapter_title: Title of the current chapter
            chapter_text: Plain text content of the chapter
            current_notes: Current notes content
            conversation_history: List of previous messages in format [{"role": "user/assistant", "content": "..."}]
            book_title: Optional book title
            quoted_text: Optional text quoted by the user
        
        Returns:
            Tuple of (response_text, updated_notes) where updated_notes is None if no update requested
        """
        # Build the system prompt
        system_prompt = self.build_system_prompt(
            chapter_title=chapter_title,
            chapter_text=chapter_text,
            current_notes=current_notes,
            book_title=book_title
        )
        
        # Prepare the message with quoted text if provided
        full_user_message = user_message
        if quoted_text:
            full_user_message = f'[Citation du texte]: "{quoted_text}"\n\n{user_message}'
        
        # Build conversation history for Gemini
        # Gemini uses a list of dicts with "role" and "parts" keys
        history = []
        
        # Add system context as first user message (Gemini doesn't have separate system role)
        history.append({"role": "user", "parts": [system_prompt]})
        history.append({"role": "model", "parts": ["Compris. Je suis prêt à discuter du chapitre."]})
        
        # Add conversation history
        for msg in conversation_history:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})
        
        try:
            # Start chat with history
            chat = self.model.start_chat(history=history)
            
            # Send current user message
            response = chat.send_message(full_user_message)
            response_text = response.text
            
            # Check if response contains NOTE_UPDATE marker
            note_update = None
            if "NOTE_UPDATE:" in response_text:
                parts = response_text.split("NOTE_UPDATE:", 1)
                response_text = parts[0].strip()
                note_update = parts[1].strip()
            
            return response_text, note_update
            
        except Exception as e:
            error_msg = f"Erreur lors de la communication avec le LLM: {str(e)}"
            return error_msg, None

