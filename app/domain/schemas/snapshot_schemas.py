from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class PostInsights(BaseModel):
    """
    Classe para insights de posts
    """
    likes: int
    reach: int
    saved: int
    shares: int
    comments: int
    total_interactions: int
    views: Optional[int] = None

class CommentData(BaseModel):
    """
    Classe para comentários em posts
    """
    id: str
    text: str
    username: str
    timestamp: str
    like_count: int

class PostData(BaseModel):
    """
    Classe para todos os dados de posts
    """
    id: str
    url: str
    type: str
    caption: str
    isVideo: bool
    comments: List[CommentData] = Field(default_factory=list)
    hashtags: List[str] = Field(default_factory=list)
    insights: PostInsights
    mentions: List[str] = Field(default_factory=list)
    shortCode: str
    timestamp: str
    likesCount: int
    commentsCount: int
    ownerUsername: str

    @property
    def caption_length(self) -> int:
        """
        Retorna o tamanho da legenda
        """
        return len(self.caption) if self.caption else 0

    @property
    def hashtags_count(self) -> int:
        """
        Retorna o numero de hashtags
        """
        return len(self.hashtags) if self.hashtags else 0
    
    @property
    def mentions_count(self) -> int:
        """
        Retorna o numero de mencoes
        """
        return len(self.mentions) if self.mentions else 0

class ProfileData(BaseModel):
    """
    Classe para dados do perfil
    """
    name: str
    website: Optional[str] = None
    biography: str
    media_count: int
    follows_count: int
    followers_count: int

class SnapshotsData(BaseModel):
    """
    Classe principal para dados de snapshot
    """
    username: str
    collected_at: str
    profile: ProfileData
    posts: List[PostData]
    total_posts: int
