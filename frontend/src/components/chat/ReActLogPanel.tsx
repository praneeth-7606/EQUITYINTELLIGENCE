import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Step } from '../../store/appStore';

interface ReActLogPanelProps {
  steps: Step[];
}

export default function ReActLogPanel({ steps }: ReActLogPanelProps) {
  const [expanded, setExpanded] = useState(false);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-muted hover:text-gold transition-colors flex items-center gap-1.5"
        aria-expanded={expanded}
        aria-controls="react-log"
      >
        <span className="text-[10px]">{expanded ? '▼' : '▶'}</span>
        <span>Show reasoning ({steps.length} step{steps.length !== 1 ? 's' : ''})</span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            id="react-log"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-2 bg-canvas/80 rounded-lg border border-border/50 p-3 space-y-1.5
                            max-h-80 overflow-y-auto">
              {steps.map((step, i) => (
                <div key={i} className="space-y-0.5">
                  {step.thought && (
                    <div className="flex gap-2 text-[11px] font-data leading-relaxed">
                      <span className="text-muted shrink-0 w-12">Step {step.step_num}</span>
                      <span className="bg-raised/50 text-muted px-1.5 py-0.5 rounded text-[10px] shrink-0">
                        THOUGHT
                      </span>
                      <span className="text-muted/80">{step.thought}</span>
                    </div>
                  )}
                  {step.action && (
                    <div className="flex gap-2 text-[11px] font-data leading-relaxed">
                      <span className="text-muted shrink-0 w-12">Step {step.step_num}</span>
                      <span className="bg-gold/20 text-gold px-1.5 py-0.5 rounded text-[10px] shrink-0">
                        ACTION
                      </span>
                      <span className="text-gold/80">{step.action}</span>
                    </div>
                  )}
                  {step.tool_input && (
                    <div className="flex gap-2 text-[11px] font-data leading-relaxed">
                      <span className="text-muted shrink-0 w-12">Step {step.step_num}</span>
                      <span className="bg-raised/50 text-muted px-1.5 py-0.5 rounded text-[10px] shrink-0">
                        INPUT
                      </span>
                      <span className="text-muted/60 truncate max-w-[300px]">{step.tool_input}</span>
                    </div>
                  )}
                  {step.observation && (
                    <div className="flex gap-2 text-[11px] font-data leading-relaxed">
                      <span className="text-muted shrink-0 w-12">Step {step.step_num}</span>
                      <span className="bg-raised/50 text-muted px-1.5 py-0.5 rounded text-[10px] shrink-0">
                        OBS
                      </span>
                      <span className="text-muted/60 truncate max-w-[300px]">
                        {step.observation.length > 100
                          ? step.observation.slice(0, 100) + '…'
                          : step.observation
                        }
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
