import { Calendar } from "@/components/ui/calendar"
import { useSidebar } from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"

export function TimelineSidebarCalendar({ date, onDateChange }: { date: Date, onDateChange: (date: Date) => void }) {
  const { state } = useSidebar()

  if (state === "collapsed") {
    return null
  }

  return (
    <div className={cn("flex justify-center py-4", state === "expanded" && "animate-in fade-in")}>
      <Calendar
        mode="single"
        selected={date}
        onSelect={(d) => d && onDateChange(d)}
        required
        className="rounded-md"
      />
    </div>
  )
}
