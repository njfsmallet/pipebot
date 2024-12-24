class TokenEstimator:
    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
            
        words = text.split()
        word_count = len(words)
        
        char_count = len(''.join(words))
        
        punctuation = sum(1 for c in text if c in '.,!?;:()[]{}"\'-')
        
        estimated_tokens = (
            word_count +
            punctuation +
            (char_count // 4)
        )
        
        return estimated_tokens 