import { useCallback, useEffect, useRef, useState } from 'react';

interface GeocodeSuggestion {
  display_name: string;
  city: string;
  country: string;
  lat: number;
  lon: number;
  timezone: string;
}

interface BirthData {
  date: string;
  time: string;
  city: string;
  lat: number;
  lon: number;
  timezone: string;
}

interface OnboardingScreenProps {
  apiBaseUrl: string;
  onSessionStart: (sessionId: string, token: string) => void;
}

export function OnboardingScreen({ apiBaseUrl, onSessionStart }: OnboardingScreenProps) {
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [cityQuery, setCityQuery] = useState('');
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [selectedCity, setSelectedCity] = useState<GeocodeSuggestion | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced city autocomplete
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (cityQuery.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`${apiBaseUrl}/api/geocode?city=${encodeURIComponent(cityQuery)}`);
        if (res.ok) {
          const data = (await res.json()) as GeocodeSuggestion[];
          setSuggestions(data);
          setShowSuggestions(true);
        }
      } catch {
        // Silently ignore fetch errors for autocomplete
      }
    }, 300);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [cityQuery, apiBaseUrl]);

  const handleCitySelect = useCallback((suggestion: GeocodeSuggestion) => {
    setSelectedCity(suggestion);
    setCityQuery(suggestion.city || suggestion.display_name);
    setShowSuggestions(false);
    setSuggestions([]);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!date || !time || !selectedCity) {
      setError('Заполните все поля');
      return;
    }

    setLoading(true);
    setError(null);

    const birthData: BirthData = {
      date,
      time,
      city: selectedCity.city || selectedCity.display_name,
      lat: selectedCity.lat,
      lon: selectedCity.lon,
      timezone: selectedCity.timezone,
    };

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const initData = window.Telegram?.WebApp?.initData;
      if (initData) {
        headers['X-Telegram-Init-Data'] = initData;
      }

      const res = await fetch(`${apiBaseUrl}/api/session/start`, {
        method: 'POST',
        headers,
        body: JSON.stringify(birthData),
      });

      if (!res.ok) {
        throw new Error('Ошибка запуска сессии');
      }

      const result = (await res.json()) as { session_id: string; token: string };
      onSessionStart(result.session_id, result.token);
    } catch {
      setError('Не удалось начать сессию. Попробуйте снова.');
    } finally {
      setLoading(false);
    }
  }, [date, time, selectedCity, apiBaseUrl, onSessionStart]);

  return (
    <div className="flex min-h-screen flex-col bg-[#1c1c1e] text-white">
      {/* Cosmic header */}
      <div className="relative flex h-48 items-center justify-center overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-purple-900/60 via-blue-900/40 to-[#1c1c1e]" />
        <div className="absolute inset-0 opacity-30">
          <div className="absolute left-[10%] top-[20%] h-1 w-1 animate-pulse rounded-full bg-white" />
          <div className="absolute left-[30%] top-[40%] h-1.5 w-1.5 animate-pulse rounded-full bg-purple-300" style={{ animationDelay: '0.5s' }} />
          <div className="absolute left-[60%] top-[15%] h-1 w-1 animate-pulse rounded-full bg-blue-300" style={{ animationDelay: '1s' }} />
          <div className="absolute left-[80%] top-[35%] h-1 w-1 animate-pulse rounded-full bg-white" style={{ animationDelay: '1.5s' }} />
          <div className="absolute left-[45%] top-[60%] h-1.5 w-1.5 animate-pulse rounded-full bg-purple-200" style={{ animationDelay: '2s' }} />
          <div className="absolute left-[70%] top-[55%] h-1 w-1 animate-pulse rounded-full bg-blue-200" style={{ animationDelay: '0.8s' }} />
        </div>
        <div className="relative z-10 text-center">
          <div className="mb-2 text-5xl">&#x2728;</div>
          <h1 className="text-2xl font-bold">&#x0421;&#x0442;&#x0435;&#x043B;&#x043B;&#x0430;</h1>
          <p className="mt-1 text-sm text-purple-200">&#x0412;&#x0430;&#x0448; &#x043B;&#x0438;&#x0447;&#x043D;&#x044B;&#x0439; &#x0430;&#x0441;&#x0442;&#x0440;&#x043E;&#x043B;&#x043E;&#x0433;</p>
        </div>
      </div>

      {/* Form */}
      <div className="flex flex-1 flex-col px-6 pb-8">
        <h2 className="mb-6 text-center text-lg font-semibold text-purple-200">
          &#x0412;&#x0432;&#x0435;&#x0434;&#x0438;&#x0442;&#x0435; &#x0434;&#x0430;&#x043D;&#x043D;&#x044B;&#x0435; &#x0440;&#x043E;&#x0436;&#x0434;&#x0435;&#x043D;&#x0438;&#x044F;
        </h2>

        {/* Date picker */}
        <div className="mb-4">
          <label className="mb-1 block text-sm text-gray-400">&#x0414;&#x0430;&#x0442;&#x0430; &#x0440;&#x043E;&#x0436;&#x0434;&#x0435;&#x043D;&#x0438;&#x044F;</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-[#2c2c2e] px-4 py-3 text-white outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
          />
        </div>

        {/* Time picker */}
        <div className="mb-4">
          <label className="mb-1 block text-sm text-gray-400">&#x0412;&#x0440;&#x0435;&#x043C;&#x044F; &#x0440;&#x043E;&#x0436;&#x0434;&#x0435;&#x043D;&#x0438;&#x044F;</label>
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-[#2c2c2e] px-4 py-3 text-white outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
          />
        </div>

        {/* City autocomplete */}
        <div className="relative mb-6">
          <label className="mb-1 block text-sm text-gray-400">&#x0413;&#x043E;&#x0440;&#x043E;&#x0434; &#x0440;&#x043E;&#x0436;&#x0434;&#x0435;&#x043D;&#x0438;&#x044F;</label>
          <input
            type="text"
            value={cityQuery}
            onChange={(e) => {
              setCityQuery(e.target.value);
              setSelectedCity(null);
            }}
            onFocus={() => {
              if (suggestions.length > 0) setShowSuggestions(true);
            }}
            placeholder="&#x041D;&#x0430;&#x0447;&#x043D;&#x0438;&#x0442;&#x0435; &#x0432;&#x0432;&#x043E;&#x0434;&#x0438;&#x0442;&#x044C; &#x043D;&#x0430;&#x0437;&#x0432;&#x0430;&#x043D;&#x0438;&#x0435;..."
            className="w-full rounded-xl border border-white/10 bg-[#2c2c2e] px-4 py-3 text-white outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
          />
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-20 mt-1 max-h-48 overflow-y-auto rounded-xl border border-white/10 bg-[#2c2c2e] shadow-lg">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleCitySelect(s)}
                  className="block w-full px-4 py-3 text-left hover:bg-purple-900/30"
                >
                  <span className="text-sm text-white">{s.city || s.display_name}</span>
                  {s.country && (
                    <span className="ml-2 text-xs text-gray-400">{s.country}</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Error message */}
        {error && (
          <p className="mb-4 text-center text-sm text-red-400">{error}</p>
        )}

        {/* Submit button */}
        <button
          onClick={handleSubmit}
          disabled={loading || !date || !time || !selectedCity}
          className="mt-auto w-full rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 py-4 text-lg font-semibold text-white shadow-lg transition-all disabled:opacity-50 disabled:shadow-none"
        >
          {loading ? '&#x0417;&#x0430;&#x043F;&#x0443;&#x0441;&#x043A;...' : '&#x041D;&#x0430;&#x0447;&#x0430;&#x0442;&#x044C; &#x043A;&#x043E;&#x043D;&#x0441;&#x0443;&#x043B;&#x044C;&#x0442;&#x0430;&#x0446;&#x0438;&#x044E; &#x2728;'}
        </button>
      </div>
    </div>
  );
}
