import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Iterator
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
        book_title: Optional[str] = None,
        include_chapter: bool = True,
        include_notes: bool = True
    ) -> str:
        """Build the system prompt with chapter context and current notes."""
        
        prompt = f"""Tu es un assistant de lecture intelligent."""
        
        if book_title:
            prompt += f" L'utilisateur lit le livre '{book_title}'"
            
        if include_chapter:
            # Truncate chapter text if too long (keep first 8000 chars to leave room for notes and conversation)
            truncated_chapter = chapter_text[:8000]
            if len(chapter_text) > 8000:
                truncated_chapter += "\n\n[... chapter continues ...]"
            
            prompt += f""".

Tu as accès au contenu du chapitre '{chapter_title}' que l'utilisateur est en train de lire.
Voici le contenu du chapitre :

---
{truncated_chapter}
---"""
        
        if include_notes:
            prompt += f""".

Voici les notes que l'utilisateur a prises pour l'instant sur ce chapitre :

---
{current_notes if current_notes.strip() else "(Aucune note pour l'instant)"}
---"""

        prompt += "."
        return prompt
    
    def send_message(
        self,
        user_message: str,
        chapter_title: str,
        chapter_text: str,
        current_notes: str,
        conversation_history: List[Dict[str, str]],
        book_title: Optional[str] = None,
        quoted_text: Optional[str] = None,
        include_chapter: bool = True,
        include_notes: bool = True,
        snippets: List[str] = None
    ) -> str:
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
            include_chapter: Whether to include chapter text in context
            include_notes: Whether to include notes in context
            snippets: Optional list of text snippets to include in context
        
        Returns:
            Response text from the LLM
        """
        # Build the system prompt
        system_prompt = self.build_system_prompt(
            chapter_title=chapter_title,
            chapter_text=chapter_text,
            current_notes=current_notes,
            book_title=book_title,
            include_chapter=include_chapter,
            include_notes=include_notes
        )
        
        # Prepare the message with quoted text and snippets if provided
        full_user_message = user_message
        
        # Add snippets first (if any)
        if snippets and len(snippets) > 0:
            snippets_text = "\n\n".join([f'[Extrait]: "{snippet}"' for snippet in snippets])
            full_user_message = f"{snippets_text}\n\n---\n\n{full_user_message}"
        
        # Add quoted text (if any)
        if quoted_text:
            if snippets and len(snippets) > 0:
                full_user_message = f'[Citation du texte]: "{quoted_text}"\n\n{full_user_message}'
            else:
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
            return response.text
            
        except Exception as e:
            error_msg = f"Erreur lors de la communication avec le LLM: {str(e)}"
            return error_msg
    
    def send_message_stream(
        self,
        user_message: str,
        chapter_title: str,
        chapter_text: str,
        current_notes: str,
        conversation_history: List[Dict[str, str]],
        book_title: Optional[str] = None,
        quoted_text: Optional[str] = None,
        include_chapter: bool = True,
        include_notes: bool = True,
        snippets: List[str] = None
    ) -> Iterator[str]:
        """
        Send a message to the LLM and stream the response token by token.
        
        Args:
            user_message: The user's message
            chapter_title: Title of the current chapter
            chapter_text: Plain text content of the chapter
            current_notes: Current notes content
            conversation_history: List of previous messages in format [{"role": "user/assistant", "content": "..."}]
            book_title: Optional book title
            quoted_text: Optional text quoted by the user
            include_chapter: Whether to include chapter text in context
            include_notes: Whether to include notes in context
            snippets: Optional list of text snippets to include in context
        
        Yields:
            Text chunks from the LLM response
        """
        # Build the system prompt
        system_prompt = self.build_system_prompt(
            chapter_title=chapter_title,
            chapter_text=chapter_text,
            current_notes=current_notes,
            book_title=book_title,
            include_chapter=include_chapter,
            include_notes=include_notes
        )
        
        # Prepare the message with quoted text and snippets if provided
        full_user_message = user_message
        
        # Add snippets first (if any)
        if snippets and len(snippets) > 0:
            snippets_text = "\n\n".join([f'[Extrait]: "{snippet}"' for snippet in snippets])
            full_user_message = f"{snippets_text}\n\n---\n\n{full_user_message}"
        
        # Add quoted text (if any)
        if quoted_text:
            if snippets and len(snippets) > 0:
                full_user_message = f'[Citation du texte]: "{quoted_text}"\n\n{full_user_message}'
            else:
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
            
            # Send current user message with streaming
            response = chat.send_message(full_user_message, stream=True)
            
            # Yield each chunk as it arrives
            for chunk in response:
                if chunk.text:
                    yield chunk.text
                    
        except Exception as e:
            error_msg = f"Erreur lors de la communication avec le LLM: {str(e)}"
            yield error_msg

