import { Calendar } from "@/components/ui/calendar"

export function TimelineSidebarCalendar({ date, onDateChange }: { date: Date, onDateChange: (date: Date) => void }) {
  return (
    <div className="p-4">
      <Calendar
        mode="single"
        selected={date}
        onSelect={onDateChange}
        required
        className="rounded-md border shadow"
      />
    </div>
  )
}
