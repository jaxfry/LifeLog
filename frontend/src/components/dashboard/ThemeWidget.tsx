import ThemeSwitcher from "../ui/ThemeSwitcher";

export default function ThemeWidget() {
  return (
    <section
      className="border-card bg-secondary p-4 shadow-card flex flex-col gap-3"
      aria-label="Theme"
    >
      <h2 className="text-lg font-semibold text-primary mb-2">Theme</h2>
      <ThemeSwitcher />
    </section>
  );
}
