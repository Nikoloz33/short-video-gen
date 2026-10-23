import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

const snapshot = {
  project: { id: 'abc123', title: 'Kitchen' },
  status: 'awaiting_script_review',
  messages: [
    {
      role: 'agent',
      text: 'Here is the script.',
      card: { kind: 'plan', goal: 'Wash hands', steps: ['Wet'], target_sec: 45, language: 'ka' },
    },
  ],
  pending: { kind: 'script', version: 2 },
  spec: { version: 2, title: 'T', lang: 'ka', total_s: 48 },
  versions: [{ version: 2, preview: { mp4: true, vtt: true, srt: true, quiz: true }, final: null }],
  sources: [],
  cost_usd: 0.1,
};

const sseBody = (events: object[]) =>
  new ReadableStream({
    start(c) {
      c.enqueue(new TextEncoder().encode(events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')));
      c.close();
    },
  });

afterEach(() => vi.restoreAllMocks());

describe('App', () => {
  it('renders both panes, the history, quick replies and the player', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? 'GET'} ${url}`);
        if (url === '/api/projects')
          return new Response(JSON.stringify([{ id: 'abc123', title: 'Kitchen' }]));
        if (url.endsWith('/resume'))
          return new Response(
            sseBody([
              { type: 'token', text: 'Approved.' },
              {
                type: 'render_progress',
                preset: 'preview',
                version: 2,
                stage: 'render',
                renderedFrames: 5,
                totalFrames: 10,
              },
              { type: 'done', status: 'awaiting_video_review' },
            ]),
          );
        return new Response(JSON.stringify(snapshot));
      }),
    );
    render(<App />);
    expect(screen.getByLabelText('Chat')).toBeInTheDocument();
    expect(screen.getByLabelText('Video')).toBeInTheDocument();
    await screen.findByText('Here is the script.');
    expect(screen.getByText('Wash hands')).toBeInTheDocument();
    expect(screen.getByTestId('player')).toHaveAttribute(
      'src',
      expect.stringContaining('/versions/2/preview/mp4'),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Approve script' }));
    await screen.findByText('Approved.');
    await waitFor(() => expect(calls).toContain('POST /api/projects/abc123/resume'));
    expect(screen.getByLabelText('Render speed')).toHaveTextContent('5/10');
  });

  it('sends free text as a message', async () => {
    const bodies: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === '/api/projects')
          return new Response(JSON.stringify([{ id: 'abc123', title: 'Kitchen' }]));
        if (url.endsWith('/messages')) {
          bodies.push(String(init?.body));
          return new Response(sseBody([{ type: 'done', status: 'idle' }]));
        }
        return new Response(JSON.stringify({ ...snapshot, pending: null }));
      }),
    );
    render(<App />);
    await screen.findByText('Here is the script.');
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'make step 3 shorter' } });
    fireEvent.keyDown(screen.getByLabelText('Message'), { key: 'Enter' });
    await waitFor(() => expect(bodies).toEqual([JSON.stringify({ text: 'make step 3 shorter' })]));
    expect(screen.getByText('make step 3 shorter')).toBeInTheDocument();
  });
});
