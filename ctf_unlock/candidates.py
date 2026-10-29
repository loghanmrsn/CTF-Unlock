from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Dictionary:
    path: Path

    def generate(self) -> Iterator[str]:
        # Lecture bornée ligne par ligne, UTF-8 avec BOM accepté. Espaces conservés.
        with Path(self.path).open(encoding='utf-8-sig') as stream:
            while True:
                line = stream.readline(4096)
                if not line:
                    return
                value = line.rstrip('\r\n')
                if len(value) > 128 or '\x00' in value:
                    raise ValueError('Liste invalide : 128 caractères maximum par candidat, sans octet nul.')
                if value:
                    yield value

    @property
    def total(self):
        return None  # Pas de lecture préalable coûteuse ni de pourcentage inventé.


@dataclass(frozen=True)
class Mask:
    alphabet: str
    minimum: int
    maximum: int

    def validate(self):
        if not self.alphabet or len(self.alphabet) > 64 or len(set(self.alphabet)) != len(self.alphabet):
            raise ValueError('Le masque requiert 1 à 64 caractères distincts.')
        if any(c in self.alphabet for c in '\x00\r\n'):
            raise ValueError('Caractère nul et retours à la ligne interdits dans le masque.')
        if not 1 <= self.minimum <= self.maximum <= 8:
            raise ValueError('Longueurs du masque : de 1 à 8, minimum ≤ maximum.')

    @property
    def total(self):
        self.validate()
        return sum(len(self.alphabet) ** length for length in range(self.minimum, self.maximum + 1))

    def generate(self):
        self.validate()
        for length in range(self.minimum, self.maximum + 1):
            for chars in product(self.alphabet, repeat=length):
                yield ''.join(chars)
