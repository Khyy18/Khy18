import { AstroCall } from './components/AstroCall';

function App() {
  // In production, sessionId would come from URL params or Telegram start_param
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get('session') || 'default';
  const wsBase = params.get('ws') || 'ws://localhost:8000';

  return (
    <div className="h-full w-full">
      <AstroCall sessionId={sessionId} wsBaseUrl={wsBase} />
    </div>
  );
}

export default App;
