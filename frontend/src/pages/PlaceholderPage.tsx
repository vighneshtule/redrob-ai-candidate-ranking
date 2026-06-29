export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="flex h-[80vh] items-center justify-center">
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight mb-2">{title}</h1>
        <p className="text-muted-foreground">
          This module is scheduled for a future development phase.
        </p>
      </div>
    </div>
  );
}
