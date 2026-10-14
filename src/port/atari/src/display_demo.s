; Display experiment for the Atari port: show a C64 multicolour screen that is
; kept in C64 order (40 cells of 8 bytes per row) without converting it to a
; raster bitmap. Each character row is drawn in ANTIC mode 4 with the row's own
; bitmap bytes as its character set. Built and run by port/atari/display_demo.py,
; which generates tables.inc and appends the picture.
;
; A character set must start on a 1 KB boundary and holds 128 cells, so the 25
; rows are laid out three to a 1 KB block: 9 blocks from BUFFER.

        .setcpu "6502"

SDMCTL  = $022F
SDLSTL  = $0230
VDSLST  = $0200
COLOR0  = $02C4
COLOR4  = $02C8
CHBAS   = $02F4
SETVBV  = $E45C
SYSVBV  = $E45F
COLPF0  = $D016
COLPF1  = $D017
COLPF2  = $D018
COLPF3  = $D019
CHBASE  = $D409
WSYNC   = $D40A
NMIEN   = $D40E

LOAD    = $3000
BUFFER  = $4000         ; 9 KB picture, appended by the build script

row     = $80           ; next row the display-list interrupt sets up

        .org LOAD
        .byte 0                         ; boot flags
        .byte SECTORS                   ; sectors to load
        .word LOAD
        .word start                     ; DOSINI; not used, start never returns

start:  lda #0
        sta SDMCTL
        lda #<dlist
        sta SDLSTL
        lda #>dlist
        sta SDLSTL+1
        lda #<dli
        sta VDSLST
        lda #>dli
        sta VDSLST+1
        ldx #3                          ; row 0 gets its colours from the OS shadows;
:       lda row0_colours,x              ; register 3 keeps this value all frame
        sta COLOR0,x
        dex
        bpl :-
        lda #0
        sta COLOR4
        lda chbase_table
        sta CHBAS
        lda #6                          ; immediate vertical-blank vector
        ldx #>vbi
        ldy #<vbi
        jsr SETVBV
        lda #$22                        ; normal width, display on
        sta SDMCTL
        lda #$C0
        sta NMIEN
forever:
        jmp forever

vbi:    lda #1
        sta row
        jmp SYSVBV

; At the end of row n: set character set and colours for row n + 1.
; ANTIC takes about 40 of a scanline's 114 cycles for itself on these lines, so
; little may happen before WSYNC or the character set changes a line late.
; Colour register 3 (the panel) is the same for the whole frame.
dli:    pha
        txa
        pha
        ldx row
        lda chbase_table,x
        sta WSYNC
        sta CHBASE
        lda pf0_table,x
        sta COLPF0
        lda pf1_table,x
        sta COLPF1
        lda pf2_table,x
        sta COLPF2
        inc row
        pla
        tax
        pla
        rti

        .include "tables.inc"
