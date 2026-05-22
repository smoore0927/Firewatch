import { useNavigate } from 'react-router-dom'
import type { ActionQueueItem } from '@/types'
import { Badge } from '@/components/ui/badge'

interface Props {
  item: ActionQueueItem
}

export default function ActionQueueRow({ item }: Props) {
  const navigate = useNavigate()
  return (
    <button
      type="button"
      onClick={() => navigate(`/risks/${item.risk_id}`)}
      className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/40 transition-colors"
    >
      <Badge variant={item.kind === 'review' ? 'secondary' : 'outline'} className="capitalize shrink-0">
        {item.kind}
      </Badge>
      <span className="font-mono text-xs text-muted-foreground shrink-0">{item.risk_id}</span>
      <span className="font-medium text-sm flex-1 min-w-0 truncate">{item.risk_title}</span>
      <span className="text-xs text-muted-foreground shrink-0">Due {item.due_date}</span>
      <span className="text-xs font-medium text-destructive shrink-0">
        {item.days_overdue === 0 ? 'Due today' : `${item.days_overdue}d overdue`}
      </span>
    </button>
  )
}
