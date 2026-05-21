import { useCallback, useState } from 'react';
import { OnboardingScreen } from './components/OnboardingScreen';
import { AstroCall } from './components/AstroCall';

type AppState = 'onboarding' | 'call' | 'ended';

interface SessionData {
  sessionId: string;
  token: string;
}

function App() {
  const params = new URLSearchParams(window.location.search);
  const wsBase = params.get('ws') || 'ws://localhost:8000';
  const apiBase = params.get('api') || 'http://localhost:8000';

  const [appState, setAppState] = useState<AppState>('onboarding');
  const [sessionData, setSessionData] = useState<SessionData | null>(null);

  const handleSessionStart = useCallback((sessionId: string, token: string) => {
    setSessionData({ sessionId, token });
    setAppState('call');
  }, []);

  const handleCallEnd = useCallback(() => {
    setAppState('ended');
  }, []);

  const handleRestart = useCallback(() => {
    setSessionData(null);
    setAppState('onboarding');
  }, []);

  if (appState === 'onboarding') {
    return (
      <div className="h-full w-full">
        <OnboardingScreen
          apiBaseUrl={apiBase}
          onSessionStart={handleSessionStart}
        />
      </div>
    );
  }

  if (appState === 'call' && sessionData) {
    return (
      <div className="h-full w-full">
        <AstroCall
          sessionId={sessionData.sessionId}
          token={sessionData.token}
          wsBaseUrl={wsBase}
          apiBaseUrl={apiBase}
          onCallEnd={handleCallEnd}
        />
      </div>
    );
  }

  // Ended state
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#1c1c1e] p-6 text-white">
      <div className="text-center">
        <div className="mb-4 text-6xl">&#x2728;</div>
        <h2 className="mb-2 text-2xl font-bold">
          &#x041A;&#x043E;&#x043D;&#x0441;&#x0443;&#x043B;&#x044C;&#x0442;&#x0430;&#x0446;&#x0438;&#x044F; &#x0437;&#x0430;&#x0432;&#x0435;&#x0440;&#x0448;&#x0435;&#x043D;&#x0430;
        </h2>
        <p className="mb-8 text-gray-400">
          &#x0421;&#x043F;&#x0430;&#x0441;&#x0438;&#x0431;&#x043E;, &#x0447;&#x0442;&#x043E; &#x043E;&#x0431;&#x0440;&#x0430;&#x0442;&#x0438;&#x043B;&#x0438;&#x0441;&#x044C; &#x043A; &#x0421;&#x0442;&#x0435;&#x043B;&#x043B;&#x0435;!
        </p>
        <button
          onClick={handleRestart}
          className="rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 px-8 py-3 font-semibold text-white shadow-lg"
        >
          &#x041D;&#x043E;&#x0432;&#x0430;&#x044F; &#x043A;&#x043E;&#x043D;&#x0441;&#x0443;&#x043B;&#x044C;&#x0442;&#x0430;&#x0446;&#x0438;&#x044F;
        </button>
      </div>
    </div>
  );
}

export default App;
