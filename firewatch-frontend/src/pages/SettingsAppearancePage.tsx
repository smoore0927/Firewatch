import { Monitor, Moon, Sun, type LucideIcon } from 'lucide-react'
import { useTheme, type Theme } from '@/context/ThemeContext'
import { cn } from '@/lib/utils'

interface Option {
  value: Theme
  name: string
  description: string
  Icon: LucideIcon
}

const OPTIONS: Option[] = [
  {
    value: 'light',
    name: 'Light',
    description: 'Light background, dark text.',
    Icon: Sun,
  },
  {
    value: 'dark',
    name: 'Dark',
    description: 'Dark background, light text.',
    Icon: Moon,
  },
  {
    value: 'system',
    name: 'System',
    description: 'Match your operating system.',
    Icon: Monitor,
  },
]

export default function SettingsAppearancePage() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Appearance</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Choose how Firewatch looks. System matches your operating system setting.
        </p>
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm font-medium mb-2">Theme</legend>
        {OPTIONS.map(({ value, name, description, Icon }) => {
          const selected = theme === value
          return (
            <label
              key={value}
              className={cn(
                'flex items-start gap-4 rounded-md border p-4 transition-colors cursor-pointer',
                selected
                  ? 'border-primary bg-accent/50 ring-2 ring-primary'
                  : 'border-border hover:bg-accent/30',
              )}
            >
              <input
                type="radio"
                name="theme"
                value={value}
                checked={selected}
                onChange={() => setTheme(value)}
                className="sr-only"
              />
              <Icon
                className={cn(
                  'h-5 w-5 mt-0.5 shrink-0',
                  selected ? 'text-primary' : 'text-muted-foreground',
                )}
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-sm font-medium">{name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
              </div>
            </label>
          )
        })}
      </fieldset>
    </div>
  )
}
