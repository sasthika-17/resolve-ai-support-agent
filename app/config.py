import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: ROOT / '.runtime')
    api_key: str = field(default='', repr=False)
    model: str = 'gpt-4.1-mini'
    embedding_model: str = 'text-embedding-3-small'
    timeout: float = 90

    @classmethod
    def load(cls):
        load_dotenv(ROOT / '.env.local', override=False)
        return cls(data_dir=Path(os.getenv('RESOLVE_DATA_DIR', str(ROOT / '.runtime'))),
                   api_key=os.getenv('OPENAI_API_KEY', ''),
                   model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
                   embedding_model=os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'))
