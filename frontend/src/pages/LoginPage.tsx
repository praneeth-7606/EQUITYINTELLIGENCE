import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';

import { useAuth } from '../auth/AuthContext';

const featureCards = [
  {
    title: 'Traceable AI workflows',
    body: 'See which agent handled the request, which tools ran, and how long each layer took.',
  },
  {
    title: 'Portfolio intelligence',
    body: 'Upload broker statements once and reuse the prepared portfolio context across agents.',
  },
  {
    title: 'Operator-friendly console',
    body: 'Built for real work: chat, dashboards, observability, and project-linked uploads.',
  },
];

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid email or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen overflow-hidden bg-[#08111a] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.18),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(56,189,248,0.16),transparent_30%),linear-gradient(135deg,#08111a_0%,#0d1724_42%,#132235_100%)]" />
      <div className="absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,0.16)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.16)_1px,transparent_1px)] [background-size:32px_32px]" />

      <div className="relative mx-auto grid min-h-screen max-w-7xl items-center gap-10 px-6 py-10 lg:grid-cols-[1.08fr_0.92fr] lg:px-10">
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease: 'easeOut' }}
          className="space-y-8"
        >
          <div className="inline-flex items-center gap-3 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-[11px] uppercase tracking-[0.24em] text-[#c4d4df]">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            Equity Intelligence
          </div>

          <div className="space-y-5">
            <h1 className="font-display text-5xl leading-[0.95] text-white sm:text-6xl">
              Watch the portfolio backend think in real time.
            </h1>
            <p className="max-w-xl text-base leading-7 text-[#adc0cd]">
              Sign in to analyze uploaded brokerage statements, route portfolio questions through specialized agents, and inspect every LLM and tool call from the developer dashboard.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            {featureCards.map((card) => (
              <div key={card.title} className="rounded-[22px] border border-white/10 bg-white/5 p-5 backdrop-blur">
                <p className="text-sm font-semibold text-white">{card.title}</p>
                <p className="mt-2 text-xs leading-5 text-[#9fb2c0]">{card.body}</p>
              </div>
            ))}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="w-full max-w-md lg:ml-auto"
        >
          <div className="rounded-[28px] border border-white/10 bg-[#0f1824]/82 p-8 shadow-2xl shadow-black/30 backdrop-blur-2xl">
            <div className="mb-8">
              <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-emerald-500 to-sky-500 text-xl font-bold text-white shadow-lg shadow-emerald-500/20">
                EI
              </div>
              <h2 className="text-3xl font-semibold tracking-tight text-white">Welcome back</h2>
              <p className="mt-2 text-sm text-[#94a3b8]">Open your workspace and continue the analysis.</p>
            </div>

            {error && (
              <motion.div
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                className="mb-6 rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-300"
              >
                {error}
              </motion.div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9cb0be]">
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full rounded-2xl border border-white/10 bg-[#08111a] px-4 py-3 text-white outline-none transition focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20"
                  placeholder="admin@equityintel.ai"
                />
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9cb0be]">
                    Password
                  </label>
                  <span className="text-xs text-emerald-300/80">Recovery soon</span>
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full rounded-2xl border border-white/10 bg-[#08111a] px-4 py-3 text-white outline-none transition focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20"
                  placeholder="Enter your password"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center rounded-2xl bg-gradient-to-r from-emerald-500 to-sky-500 px-4 py-3.5 text-sm font-semibold tracking-wide text-white shadow-lg shadow-emerald-500/15 transition hover:from-emerald-400 hover:to-sky-400 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" /> : 'Enter Workspace'}
              </button>
            </form>

            <p className="mt-8 text-center text-sm text-[#64748b]">
              Need a new workspace?{' '}
              <Link to="/register" className="font-medium text-emerald-300 hover:underline">
                Create account
              </Link>
            </p>
          </div>
        </motion.section>
      </div>
    </div>
  );
}
