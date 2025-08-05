import React from 'react';
import { motion } from 'framer-motion';

// Composant pour afficher des dots animés améliorés
const PromptSpinner: React.FC = () => {
  return (
    <div className="prompt-spinner">
      <div className="flex space-x-1 items-center">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="w-2 h-2 bg-primary rounded-full"
            animate={{
              scale: [1, 1.2, 1],
              opacity: [0.7, 1, 0.7]
            }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              delay: i * 0.4
            }}
            style={{
              backgroundColor: 'var(--color-primary)',
            }}
          />
        ))}
      </div>
    </div>
  );
};

export default PromptSpinner;
