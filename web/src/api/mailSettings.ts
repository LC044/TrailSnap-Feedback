import { call } from './client'

export type MailAccount = {
  id?: string; name: string; host: string; port: number; username: string; password?: string;
  sender: string; tls: 'ssl' | 'starttls' | 'none'; enabled: boolean; daily_limit: number;
  has_password?: boolean; used_today?: number;
}
export type MailSettings = { source: string; accounts: MailAccount[] }
export const mailSettings = {
  get: () => call<MailSettings>('GET', '/admin/mail-settings'),
  save: (accounts: MailAccount[]) => call<MailSettings>('PUT', '/admin/mail-settings', { accounts: accounts.map(a => ({
    id: a.id, name: a.name, host: a.host, port: a.port, username: a.username, password: a.password || undefined,
    sender: a.sender, tls: a.tls, enabled: a.enabled, daily_limit: a.daily_limit,
  })) }),
}
