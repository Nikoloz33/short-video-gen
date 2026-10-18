import React from 'react';
import type { Scene } from '../spec/types';
import { Disclaimer, StepCard, Timer, TitleCard, Warning } from './Cards';
import { Checklist, DoDont, Schedule, Summary } from './Lists';
import { QuizAnswer, QuizQuestion } from './Quiz';

/** Data-driven dispatch: the LLM picks a template + fields, never a layout. */
export const SceneView: React.FC<{ scene: Scene }> = ({ scene }) => {
  switch (scene.template) {
    case 'title_card':
      return <TitleCard scene={scene} />;
    case 'step_card':
      return <StepCard scene={scene} />;
    case 'do_dont':
      return <DoDont scene={scene} />;
    case 'checklist':
      return <Checklist scene={scene} />;
    case 'warning':
      return <Warning scene={scene} />;
    case 'timer':
      return <Timer scene={scene} />;
    case 'schedule':
      return <Schedule scene={scene} />;
    case 'quiz_question':
      return <QuizQuestion scene={scene} />;
    case 'quiz_answer':
      return <QuizAnswer scene={scene} />;
    case 'summary':
      return <Summary scene={scene} />;
    case 'disclaimer':
      return <Disclaimer scene={scene} />;
  }
};
