import { useCallback, useState } from 'react';

interface PaymentPackage {
  stars: number;
  minutes: number;
  label: string;
}

const PACKAGES: PaymentPackage[] = [
  { stars: 50, minutes: 10, label: '10 \u043C\u0438\u043D' },
  { stars: 100, minutes: 25, label: '25 \u043C\u0438\u043D' },
  { stars: 200, minutes: 60, label: '60 \u043C\u0438\u043D' },
];

interface PaymentModalProps {
  apiBaseUrl: string;
  sessionId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function PaymentModal({ apiBaseUrl, sessionId, onClose, onSuccess }: PaymentModalProps) {
  const [loading, setLoading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handlePurchase = useCallback(async (pkg: PaymentPackage) => {
    setLoading(pkg.stars);
    setError(null);

    try {
      const res = await fetch(`${apiBaseUrl}/api/payments/create-invoice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          stars: pkg.stars,
          minutes: pkg.minutes,
        }),
      });

      if (!res.ok) {
        throw new Error('Failed to create invoice');
      }

      const data = (await res.json()) as { invoice_url: string };

      if (window.Telegram?.WebApp?.openInvoice) {
        window.Telegram.WebApp.openInvoice(data.invoice_url, (status: string) => {
          if (status === 'paid') {
            onSuccess();
          }
        });
      } else {
        // Fallback for non-Telegram environments
        window.open(data.invoice_url, '_blank');
      }
    } catch {
      setError('\u041D\u0435 \u0443\u0434\u0430\u043B\u043E\u0441\u044C \u0441\u043E\u0437\u0434\u0430\u0442\u044C \u043F\u043B\u0430\u0442\u0451\u0436. \u041F\u043E\u043F\u0440\u043E\u0431\u0443\u0439\u0442\u0435 \u0441\u043D\u043E\u0432\u0430.');
    } finally {
      setLoading(null);
    }
  }, [apiBaseUrl, sessionId, onSuccess]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-sm rounded-2xl bg-[#2c2c2e] p-6">
        {/* Header */}
        <div className="mb-6 text-center">
          <div className="mb-2 text-4xl">&#x2B50;</div>
          <h2 className="text-xl font-bold text-white">
            &#x041F;&#x043E;&#x043F;&#x043E;&#x043B;&#x043D;&#x0438;&#x0442;&#x044C; &#x0431;&#x0430;&#x043B;&#x0430;&#x043D;&#x0441;
          </h2>
          <p className="mt-1 text-sm text-gray-400">
            &#x0412;&#x044B;&#x0431;&#x0435;&#x0440;&#x0438;&#x0442;&#x0435; &#x043F;&#x0430;&#x043A;&#x0435;&#x0442; Telegram Stars
          </p>
        </div>

        {/* Packages */}
        <div className="mb-6 space-y-3">
          {PACKAGES.map((pkg) => (
            <button
              key={pkg.stars}
              onClick={() => handlePurchase(pkg)}
              disabled={loading !== null}
              className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-[#1c1c1e] px-4 py-4 transition-all hover:border-purple-500/50 disabled:opacity-50"
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">&#x2B50;</span>
                <div className="text-left">
                  <div className="font-semibold text-white">{pkg.stars} Stars</div>
                  <div className="text-sm text-gray-400">{pkg.label} &#x043A;&#x043E;&#x043D;&#x0441;&#x0443;&#x043B;&#x044C;&#x0442;&#x0430;&#x0446;&#x0438;&#x0438;</div>
                </div>
              </div>
              {loading === pkg.stars ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-purple-400 border-t-transparent" />
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                </svg>
              )}
            </button>
          ))}
        </div>

        {/* Error */}
        {error && (
          <p className="mb-4 text-center text-sm text-red-400">{error}</p>
        )}

        {/* Close button */}
        <button
          onClick={onClose}
          className="w-full rounded-xl border border-white/10 py-3 text-center text-gray-400 transition-colors hover:text-white"
        >
          &#x041E;&#x0442;&#x043C;&#x0435;&#x043D;&#x0430;
        </button>
      </div>
    </div>
  );
}
