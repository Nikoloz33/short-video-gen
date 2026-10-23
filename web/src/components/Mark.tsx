/**
 * Verification marks drawn after ISO 7010 sign shapes: a green disc (safe), an amber triangle
 * (caution) and a red ring with a bar (prohibition). Shape + colour, so they read without colour too.
 */
export type MarkKind = 'ok' | 'partial' | 'bad' | 'pending';

export const markOf = (verdict: string | null | undefined): MarkKind =>
  verdict === 'supported'
    ? 'ok'
    : verdict === 'partially_supported'
      ? 'partial'
      : verdict
        ? 'bad'
        : 'pending';

const TITLE: Record<MarkKind, string> = {
  ok: 'Supported by the source',
  partial: 'Partly supported',
  bad: 'Not supported by the source',
  pending: 'Not checked yet',
};

export const Mark = ({ kind, size = 16 }: { kind: MarkKind; size?: number }) => (
  <svg
    className={`mark mark-${kind}`}
    width={size}
    height={size}
    viewBox="0 0 16 16"
    role="img"
    aria-label={TITLE[kind]}
  >
    <title>{TITLE[kind]}</title>
    {kind === 'ok' ? (
      <>
        <circle cx="8" cy="8" r="7.5" fill="var(--safe)" />
        <path
          d="M4.6 8.3 7 10.6l4.4-5"
          fill="none"
          stroke="#fff"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </>
    ) : kind === 'partial' ? (
      <>
        <path
          d="M8 1.2 15.2 14H.8Z"
          fill="var(--caution)"
          stroke="var(--ink)"
          strokeWidth="1"
          strokeLinejoin="round"
        />
        <path d="M8 6v3.6" stroke="var(--ink)" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="8" cy="11.6" r=".95" fill="var(--ink)" />
      </>
    ) : kind === 'bad' ? (
      <>
        <circle cx="8" cy="8" r="6.4" fill="#fff" stroke="var(--prohibit)" strokeWidth="2.2" />
        <path d="M3.6 12.4 12.4 3.6" stroke="var(--prohibit)" strokeWidth="2.2" />
      </>
    ) : (
      <circle
        cx="8"
        cy="8"
        r="6.5"
        fill="none"
        stroke="var(--line-strong)"
        strokeWidth="1.5"
        strokeDasharray="2.4 2"
      />
    )}
  </svg>
);
