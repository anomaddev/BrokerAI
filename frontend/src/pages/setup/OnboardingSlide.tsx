import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

type OnboardingSlideProps = {
  pageKey: string;
  children: ReactNode;
};

type Frame = {
  key: string;
  node: ReactNode;
};

/**
 * Forward page transition: outgoing slides left + fades out, then the next
 * page slides in from the right + fades in (staggered so they don't overlap).
 */
export default function OnboardingSlide({ pageKey, children }: OnboardingSlideProps) {
  const [incoming, setIncoming] = useState<Frame>({ key: pageKey, node: children });
  const [outgoing, setOutgoing] = useState<Frame | null>(null);
  const [enterDelayed, setEnterDelayed] = useState(false);
  const prevKeyRef = useRef(pageKey);
  const incomingRef = useRef(incoming);
  incomingRef.current = incoming;

  useLayoutEffect(() => {
    if (pageKey === prevKeyRef.current) {
      setIncoming({ key: pageKey, node: children });
      return;
    }
    const previous = incomingRef.current;
    prevKeyRef.current = pageKey;
    setOutgoing({ key: previous.key, node: previous.node });
    setIncoming({ key: pageKey, node: children });
    setEnterDelayed(true);
  }, [pageKey, children]);

  return (
    <div className={`onboarding-slide-stage${outgoing ? " is-transitioning" : ""}`}>
      {outgoing && (
        <div
          key={`out-${outgoing.key}`}
          className="onboarding-slide onboarding-slide--exit"
          onAnimationEnd={(event) => {
            if (event.target !== event.currentTarget) return;
            setOutgoing(null);
          }}
          aria-hidden
        >
          {outgoing.node}
        </div>
      )}
      <div
        key={`in-${incoming.key}`}
        className={`onboarding-slide onboarding-slide--enter${
          enterDelayed ? " onboarding-slide--enter-delayed" : ""
        }`}
        onAnimationEnd={(event) => {
          if (event.target !== event.currentTarget) return;
          setEnterDelayed(false);
        }}
      >
        {incoming.node}
      </div>
    </div>
  );
}
