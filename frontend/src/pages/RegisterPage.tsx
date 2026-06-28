import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';

import { useAuth } from '../auth/AuthContext';

export default function RegisterPage() {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register(email, username, fullName, password);
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed. Check inputs.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen overflow-hidden bg-[#08111a] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(16,185,129,0.16),transparent_32%),linear-gradient(135deg,#08111a_0%,#101927_46%,#162437_100%)]" />
      <div className="absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,0.16)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.16)_1px,transparent_1px)] [background-size:32px_32px]" />

      <div className="relative mx-auto grid min-h-screen max-w-7xl items-center gap-10 px-6 py-10 lg:grid-cols-[0.96fr_1.04fr] lg:px-10">
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease: 'easeOut' }}
          className="order-2 w-full max-w-md lg:order-1"
        >
          <div className="rounded-[28px] border border-white/10 bg-[#0f1824]/82 p-8 shadow-2xl shadow-black/30 backdrop-blur-2xl">
            <div className="mb-8">
              <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-sky-500 to-emerald-500 text-xl font-bold text-white shadow-lg shadow-sky-500/20">
                EI
              </div>
              <h2 className="text-3xl font-semibold tracking-tight text-white">Create account</h2>
              <p className="mt-2 text-sm text-[#94a3b8]">Set up your portfolio intelligence workspace.</p>
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

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9cb0be]">
                  Full name
                </label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  className="w-full rounded-2xl border border-white/10 bg-[#08111a] px-4 py-3 text-white outline-none transition focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20"
                  placeholder="Praneeth V"
                />
              </div>

              <div>
                <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9cb0be]">
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  className="w-full rounded-2xl border border-white/10 bg-[#08111a] px-4 py-3 text-white outline-none transition focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20"
                  placeholder="praneeth"
                />
              </div>

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
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9cb0be]">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full rounded-2xl border border-white/10 bg-[#08111a] px-4 py-3 text-white outline-none transition focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20"
                  placeholder="Minimum 8 characters"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="mt-2 flex w-full items-center justify-center rounded-2xl bg-gradient-to-r from-sky-500 to-emerald-500 px-4 py-3.5 text-sm font-semibold tracking-wide text-white shadow-lg shadow-sky-500/15 transition hover:from-sky-400 hover:to-emerald-400 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" /> : 'Create Workspace'}
              </button>
            </form>

            <p className="mt-8 text-center text-sm text-[#64748b]">
              Already registered?{' '}
              <Link to="/login" className="font-medium text-emerald-300 hover:underline">
                Sign in
              </Link>
            </p>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          className="order-1 space-y-8 lg:order-2"
        >
          <div className="inline-flex items-center gap-3 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-[11px] uppercase tracking-[0.24em] text-[#c4d4df]">
            <span className="h-2 w-2 rounded-full bg-sky-400" />
            Operating Layer for Portfolios
          </div>

          <div className="space-y-5">
            <h1 className="font-display text-5xl leading-[0.95] text-white sm:text-6xl">
              Build one workspace for uploads, agents, and observability.
            </h1>
            <p className="max-w-xl text-base leading-7 text-[#adc0cd]">
              Create an account to organize projects, upload brokerage statements, compare stocks, and inspect every backend decision from route selection to final report generation.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            {[
              ['Project-linked uploads', 'Group brokerage sheets into reusable portfolio workstreams.'],
              ['Agent-first answers', 'Route questions to dedicated portfolio, P&L, dividend, or stock-analysis agents.'],
              ['Developer visibility', 'See provider, model, tools, tokens, cost, and latency for each run.'],
            ].map(([title, body]) => (
              <div key={title} className="rounded-[22px] border border-white/10 bg-white/5 p-5 backdrop-blur">
                <p className="text-sm font-semibold text-white">{title}</p>
                <p className="mt-2 text-xs leading-5 text-[#9fb2c0]">{body}</p>
              </div>
            ))}
          </div>
        </motion.section>
      </div>
    </div>
  );
}
