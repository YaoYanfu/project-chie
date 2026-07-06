import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Shield, User, Lock, LogIn } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { isElectron } from '@/lib/runtime'

export function AmadeusAuthPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isSetup, setIsSetup] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const setupChecked = useRef(false)

  // 检查是否需要首次配置 + 是否已登录
  useEffect(() => {
    if (setupChecked.current) return
    setupChecked.current = true

    // 先检查是否已经登录
    fetch('/api/webui/auth/check', { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        if (data.authenticated) {
          navigate({ to: '/amadeus' })
          return
        }
        // 未登录，检查 Amadeus 是否已配置
        return fetch('/api/webui/amadeus/auth/configured', { credentials: 'include' })
          .then(r => r.json())
          .then(cfg => {
            setIsSetup(!cfg.configured)
            setIsLoading(false)
          })
      })
      .catch(() => setIsLoading(false))
  }, [navigate])

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码')
      return
    }
    setIsSubmitting(true)
    try {
      const endpoint = isSetup
        ? '/api/webui/amadeus/auth/setup'
        : '/api/webui/amadeus/auth/login'
      const r = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username: username.trim(), password }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || '认证失败')
      navigate({ to: '/amadeus' })
    } catch (err) {
      setError(err instanceof Error ? err.message : '连接失败')
    } finally {
      setIsSubmitting(false)
    }
  }, [username, password, isSetup, navigate])

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0d0b10]">
        <div className="text-white/40 text-sm">Amadeus</div>
      </div>
    )
  }

  return (
    <div className="flex h-screen items-center justify-center bg-[#0d0b10] p-4">
      {/* 背景装饰 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-rose-500/10 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-teal-500/10 blur-3xl" />
      </div>

      <Card className="relative z-10 w-full max-w-sm border-white/10 bg-white/5 backdrop-blur-xl shadow-2xl">
        <CardHeader className="space-y-3 text-center pb-2">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/15">
            <Shield className="h-7 w-7 text-rose-400" strokeWidth={1.5} fill="none" />
          </div>
          <div>
            <CardTitle className="text-xl font-bold text-white">
              {isSetup ? '首次配置 · Amadeus' : 'Amadeus'}
            </CardTitle>
            <CardDescription className="text-white/50 text-sm mt-1">
              {isSetup ? '设置管理员账户以保护千惠' : 'AI 实体管理 · 千惠'}
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-white/70 text-xs font-medium">用户名</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/30" strokeWidth={1.5} />
                <Input
                  id="username"
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  className={cn('pl-10 bg-white/5 border-white/10 text-white placeholder:text-white/25',
                    error && 'border-red-500/60')}
                  disabled={isSubmitting}
                  autoFocus
                  autoComplete="username"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-white/70 text-xs font-medium">密码</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/30" strokeWidth={1.5} />
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className={cn('pl-10 bg-white/5 border-white/10 text-white placeholder:text-white/25',
                    error && 'border-red-500/60')}
                  disabled={isSubmitting}
                  autoComplete={isSetup ? 'new-password' : 'current-password'}
                />
              </div>
            </div>

            {error && (
              <div className="rounded-md bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400">
                {error}
              </div>
            )}

            <Button type="submit" className="w-full bg-rose-600 hover:bg-rose-500 text-white" disabled={isSubmitting}>
              {isSubmitting ? (
                <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              ) : (
                <LogIn className="h-4 w-4 mr-2" strokeWidth={1.5} />
              )}
              {isSetup ? '创建账户' : '登入'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="absolute bottom-6 text-white/20 text-xs">
        Amadeus System · {isElectron() ? 'Desktop' : 'Web'}
      </div>
    </div>
  )
}
