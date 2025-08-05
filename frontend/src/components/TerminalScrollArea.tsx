"use client"

import * as React from "react"
import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area"

// Utility function for cn
function cn(...classes: (string | undefined | null | boolean)[]): string {
  return classes.filter(Boolean).join(' ')
}

interface TerminalScrollbarProps {
  className?: string
  children?: React.ReactNode
  height?: string | number
  showScrollbar?: boolean
  terminalTheme?: 'dark' | 'matrix' | 'cyberpunk'
}

const TerminalScrollArea = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.Root>,
  TerminalScrollbarProps & React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root>
>(({ className, children, height = "400px", showScrollbar = true, terminalTheme = 'dark', ...props }, ref) => (
  <ScrollAreaPrimitive.Root
    ref={ref}
    className={cn("relative overflow-hidden", className)}
    style={{ height }}
    {...props}
  >
    <ScrollAreaPrimitive.Viewport className="h-full w-full rounded-[inherit]">
      {children}
    </ScrollAreaPrimitive.Viewport>
    {showScrollbar && <TerminalScrollBar terminalTheme={terminalTheme} />}
    <ScrollAreaPrimitive.Corner className="bg-background" />
  </ScrollAreaPrimitive.Root>
))
TerminalScrollArea.displayName = "TerminalScrollArea"

const TerminalScrollBar = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar> & {
    terminalTheme?: 'dark' | 'matrix' | 'cyberpunk'
  }
>(({ className, orientation = "vertical", terminalTheme = 'dark', ...props }, ref) => {
  const getThemeClasses = () => {
    switch (terminalTheme) {
      case 'matrix':
        return {
          track: "bg-black/20 border-green-500/30",
          thumb: "bg-green-500/80 shadow-[0_0_8px_rgba(34,197,94,0.6)] hover:bg-green-400/90 hover:shadow-[0_0_12px_rgba(34,197,94,0.8)]"
        }
      case 'cyberpunk':
        return {
          track: "bg-purple-950/30 border-cyan-500/30",
          thumb: "bg-gradient-to-b from-cyan-400 to-purple-500 shadow-[0_0_8px_rgba(6,182,212,0.6)] hover:shadow-[0_0_12px_rgba(6,182,212,0.8)]"
        }
      default:
        return {
          track: "bg-gray-900/20 border-gray-600/30",
          thumb: "bg-gray-400/80 shadow-[0_0_4px_rgba(156,163,175,0.4)] hover:bg-gray-300/90 hover:shadow-[0_0_6px_rgba(156,163,175,0.6)]"
        }
    }
  }

  const themeClasses = getThemeClasses()

  return (
    <ScrollAreaPrimitive.ScrollAreaScrollbar
      ref={ref}
      orientation={orientation}
      className={cn(
        "flex touch-none select-none transition-all duration-300 ease-out",
        "border border-transparent rounded-full",
        orientation === "vertical" &&
          "h-full w-3 border-l border-l-transparent p-[2px] hover:w-4",
        orientation === "horizontal" &&
          "h-3 flex-col border-t border-t-transparent p-[2px] hover:h-4",
        themeClasses.track,
        className,
      )}
      {...props}
    >
      <ScrollAreaPrimitive.ScrollAreaThumb 
        className={cn(
          "relative flex-1 rounded-full transition-all duration-200 ease-out",
          "before:absolute before:left-1/2 before:top-1/2 before:h-full before:min-h-[44px] before:w-full before:min-w-[44px] before:-translate-x-1/2 before:-translate-y-1/2 before:content-['']",
          themeClasses.thumb
        )} 
      />
    </ScrollAreaPrimitive.ScrollAreaScrollbar>
  )
})
TerminalScrollBar.displayName = "TerminalScrollBar"

export { TerminalScrollArea, TerminalScrollBar } 