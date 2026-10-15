"use client";

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { activeIds, endDrag, getRecordIds, hasRecordIds } from "@/lib/dragPayload";

interface FolderDropOptions {
  /** False when the target must ignore drags entirely (prop not provided). */
  droppable: boolean;
  /** Called with the dropped record ids when the drop lands here. */
  onDropRecords: (recordIds: string[]) => void;
}

/**
 * HTML5 drop-target behaviour for a folder card: highlight while a gallery
 * selection hovers, decode the ids on drop.
 *
 * `dragenter`/`dragleave` fire for every child element the pointer crosses, so
 * a depth counter decides when the pointer has truly entered/left the card. A
 * cancelled drag (Esc) fires `dragend` on the *source* and no reliable leave
 * events on the target — the document-level listeners reset the highlight so
 * it can never stick.
 */
export function useFolderDrop({ droppable, onDropRecords }: FolderDropOptions) {
  const [dragOver, setDragOver] = useState(false);
  const [dropCount, setDropCount] = useState(0);
  const depth = useRef(0);

  const reset = useCallback(() => {
    depth.current = 0;
    setDragOver(false);
    setDropCount(0);
  }, []);

  useEffect(() => {
    document.addEventListener("dragend", reset);
    document.addEventListener("drop", reset);
    return () => {
      document.removeEventListener("dragend", reset);
      document.removeEventListener("drop", reset);
    };
  }, [reset]);

  const onDragEnter = useCallback(
    (event: DragEvent) => {
      if (!droppable || !hasRecordIds(event.dataTransfer)) return;
      event.preventDefault();
      depth.current += 1;
      setDragOver(true);
      setDropCount(activeIds().length);
    },
    [droppable]
  );

  const onDragOver = useCallback(
    (event: DragEvent) => {
      if (!droppable || !hasRecordIds(event.dataTransfer)) return;
      // Without preventDefault the browser refuses the drop entirely.
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    },
    [droppable]
  );

  const onDragLeave = useCallback(() => {
    depth.current = Math.max(0, depth.current - 1);
    if (depth.current === 0) reset();
  }, [reset]);

  const onDrop = useCallback(
    (event: DragEvent) => {
      const ids = getRecordIds(event.dataTransfer);
      reset();
      if (!droppable || ids.length === 0) return;
      event.preventDefault();
      event.stopPropagation();
      endDrag();
      onDropRecords(ids);
    },
    [droppable, onDropRecords, reset]
  );

  return { dragOver, dropCount, onDragEnter, onDragOver, onDragLeave, onDrop };
}
