; Title stage of the Atari build: runs the C64 title program (side A block 0,
; $4000-$4F7F) before the game is loaded. Design: docs/TITLE.md.
; Built by port/atari/build.py, which supplies config.inc, kernel.inc (the
; kernel's labels) and title-music.inc.
;
; The title program is the original's, with only its video, sound and CIA
; operands pointed at the kernel's stand-in registers, as in the game. It
; draws into the C64's lower bitmap ($E000, colours at $CC00 and $D800), which
; is what the kernel's screen copy already knows how to show. This file is
; what the kernel does not have room for:
;
;   the two title frames   shown where they are. Their cells all use the same
;                          three colours, so a row of the C64 bitmap is an
;                          ANTIC mode 4 character set as it stands. Six rows
;                          cross a 1 KB boundary and are copied to a buffer.
;   the scenes             converted by the kernel's own screen copy, once the
;                          title program has finished drawing each one.
;   the tune               three SID voices, translated to POKEY every frame.
;   leaving                the key reader ends the stage when Escape arrives,
;                          and the boot code goes on to load the game.
;
; Loaded at $8000 by boot.s, which first parks itself at PARK: the title
; program uses the boot code's memory for its pictures. Nothing here may be
; in $4000-$7FFF, where the CPU sees the extended bank during a screen copy.

        .setcpu "6502"
        .include "config.inc"
        .include "kernel.inc"

COLPF0  = $D016
COLPF1  = $D017
COLPF2  = $D018
COLPF3  = $D019
COLBK   = $D01A
AUDF1   = $D200
AUDC1   = $D201
PORTB   = $D301
DMACTL  = $D400
DLISTL  = $D402
DLISTH  = $D403
CHBASE  = $D409
WSYNC   = $D40A
NMIEN   = $D40E
NMIRES  = $D40F
NMIST   = $D40F
PB_GAME     = $D2
PB_GAME_EXT = $C2

KEY_COUNT    = $C6
KEY_BUFFER   = $0277
KEY_REPEAT   = $028A
IRQ_VECTOR   = $0314
DISPLAY_MODE = $0389
NMI_VECTOR   = $FFFA
GETIN_JUMP   = $FFE4            ; the kernel's JMP getin
READ_JUMP    = $9D0D            ; the kernel's JMP disk_read
PICTURE      = $4000            ; in the extended bank: the kernel's screen
TITLE_START  = $4000            ; the title program
BITMAP       = $E000            ; where it draws
BUFFER       = $1400            ; two 1 KB character sets for the six copied rows
PARKED       = BOOT_LOAD
PARK_PAGES   = BOOT_SECTORS / 2

; Where the title program waits between two scenes ($4168-$417A, six calls of
; a counting loop), and the pages its drawing code is in. Between two title
; frames it waits in $4197-$41C9.
HOLD_FIRST   = $4168
HOLD_END     = $417B
WAIT_FIRST   = $4197
WAIT_END     = $41CA
DRAW_FIRST   = $43
DRAW_END     = $49

        .segment "TITLE"
        .org TITLE_AT           ; fixed: the handler below is placed by its address
entry:  jmp start
resume: .word 0                 ; set by boot.s: where it goes on after the title

; --- display ---------------------------------------------------------------
; The title frames: 25 rows of ANTIC mode 4, as the kernel's play screen, but
; each row's character set is the C64 bitmap row itself. Row r is at
; $E000 + 320 r; its 1 KB block and the code of its first cell follow from
; that. Rows 3, 6, 9, 12, 19 and 22 would run over the end of their block:
; they are shown from BUFFER, three rows to a block.
; at0-at24: where ANTIC reads each row from. slot counts the copied rows.
        .repeat 25, r
        .if ((320 * r) .mod 1024) > 704
slot .set (r > 3) + (r > 6) + (r > 9) + (r > 12) + (r > 19)
.ident(.sprintf("at%d", r)) = BUFFER + (slot / 3) * $400 + (slot .mod 3) * 320
        .else
.ident(.sprintf("at%d", r)) = BITMAP + 320 * r
        .endif
        .endrepeat

list:   .byte $70, $70          ; 16 blank lines, as the kernel's lists
        .repeat 25, r
        .if r < 24
        .byte $C4               ; mode 4, load address, interrupt
        .else
        .byte $44
        .endif
        .word codes + (.ident(.sprintf("at%d", r)) .mod 1024) / 8
        .endrepeat
        .byte $41
        .word list
list_end:
        .assert >list = >(list_end - 1), error, "the display list crosses a page"
codes:  .repeat 128, i
        .byte i
        .endrepeat
chbase: .repeat 25, r
        .byte >.ident(.sprintf("at%d", r)) & $FC
        .endrepeat

; The interrupt handler while the title frames are shown. Its address differs
; from the kernel's `nmi` in the high byte only, so that one store changes
; handlers; a two-byte change could be interrupted half way.
        .res (<nmi - <*) & $FF
title_nmi:
        .assert <title_nmi = <nmi, error, "title_nmi must share the low byte of nmi"
        bit NMIST
        bvs title_vbi
        pha                     ; end of a row: the next row's character set.
        txa                     ; The same instructions as the kernel's, for
        pha                     ; the same reason (docs/ATARI-DESIGN.md).
        ldx t_row
        lda chbase,x
        sta WSYNC
        sta CHBASE
        inc t_row
        sta NMIRES
        pla
        tax
        pla
        rti

title_vbi:
        pha
        txa
        pha
        tya
        pha
        sta NMIRES
        cld
        lda #<list
        sta DLISTL
        lda #>list
        sta DLISTH
        lda chbase
        sta CHBASE
        lda #TITLE_PF0
        sta COLPF0
        lda #TITLE_PF1
        sta COLPF1
        lda #TITLE_PF2
        sta COLPF2
        sta COLPF3
        lda #0
        sta COLBK
        lda #1
        sta t_row
        lda #$C0
        ldx #$22
        ldy stage
        beq :+
        ; A scene is being prepared: black until it is ready. With its DMA off
        ; ANTIC repeats the instruction it had, and if that was a row with an
        ; interrupt it interrupts every eight lines for good. The one before
        ; the vertical blank would still be running when this handler starts,
        ; which would look below like a program with interrupts masked, every
        ; frame (seen in AltirraSDL; Atari800 does not do this). So none.
        lda #$40
        ldx #0
:       sta NMIEN
        stx DMACTL
        jsr music               ; whatever the title program's interrupts are doing
        lda stage
        bne @chain
        lda fake_sid+$18
        and #$0F
        bne @show
        inc stage               ; the tune was stopped: SPACE. Scenes come next.
        lda #0
        sta fresh
        beq @chain
@show:  tsx                     ; the six copied rows, two a frame, while the
        lda $0106,x             ; title program draws and once more after it
        cmp #>WAIT_FIRST        ; has stopped. While it waits the frame is
        bne @drawn              ; complete and its counting loop gets the time,
        lda $0105,x             ; as on the C64.
        cmp #<WAIT_FIRST
        bcc @drawn
        cmp #<WAIT_END
        bcc :+
@drawn: lda #3
        sta passes
:       lda passes
        beq @chain
        dec passes
        jsr copy_two
@chain: tsx
        lda $0104,x             ; flags of the interrupted code
        and #$04
        bne @masked             ; it had interrupts masked; a C64 would wait
        jsr keyboard
        jmp (IRQ_VECTOR)        ; the title program's tune, then `tick`
@masked:
        jmp leave

; Two of the six copied rows per frame: all six every three frames.
copy_two:
        jsr @one
@one:   ldx next
        dex
        bpl :+
        ldx #5
:       stx next
        lda copy_low,x
        sta @go+1
        lda copy_high,x
        sta @go+2
@go:    jmp $FFFF

.macro COPY_ROW r
        .local from, to, again
from = BITMAP + 320 * r
to   = .ident(.sprintf("at%d", r))
        ldx #160
again:  lda from - 1,x
        sta to - 1,x
        lda from + 159,x
        sta to + 159,x
        dex
        bne again
        rts
.endmacro
copy0:  COPY_ROW 3
copy1:  COPY_ROW 6
copy2:  COPY_ROW 9
copy3:  COPY_ROW 12
copy4:  COPY_ROW 19
copy5:  COPY_ROW 22
copy_low:   .lobytes copy0, copy1, copy2, copy3, copy4, copy5
copy_high:  .hibytes copy0, copy1, copy2, copy3, copy4, copy5

; --- once a frame, after the title program's own interrupt handler ---------
; Reached through $0314 as the KERNAL's handler is on the C64, so only while
; the title program has interrupts enabled. stage: 0 the title frames are
; shown; 1 black, waiting for the first scene; 2 a scene is shown by the
; kernel's handlers.
tick:   cld
        lda stage
        beq @done
        lda fake_sid+$18
        and #$0F
        beq :+
        jmp to_title            ; the tune has been started again
:       lda busy
        bne @done               ; this is a frame during our own screen copy
        tsx
        lda $0106,x             ; where the title program was interrupted
        cmp #>HOLD_FIRST
        bne @drawing
        lda $0105,x
        cmp #<HOLD_FIRST
        bcc @done
        cmp #<HOLD_END
        bcs @done
        lda fresh               ; it is waiting: the scene is complete
        bne @done
        lda IRQ_VECTOR          ; the copy runs with the title program's memory
        cmp #<tick              ; switched out: none of its code may be called
        bne @done
        lda IRQ_VECTOR+1
        cmp #>tick
        bne @done
        inc busy
        cli                     ; keys are still read while the copy runs
        lda stage
        cmp #2
        beq :+
        lda #0                  ; the first scene: every row's colours are
        sta shown_mode          ; chosen anew, nothing is reused
:       jsr portraits
        lda #PB_GAME_EXT
        sta PORTB
        lda #1                  ; the lower bitmap on the whole frame
        jsr rf_bitmap
        lda #PB_GAME
        sta PORTB
        sei
        lda #>nmi
        sta NMI_VECTOR+1
        lda #2
        sta stage
        sta fresh
        lda #0
        sta busy
@done:  jmp leave
@drawing:
        cmp #DRAW_FIRST
        bcc @done
        cmp #DRAW_END
        bcs @done
        lda #0                  ; a new scene is being drawn
        sta fresh
        beq @done

; Back at the title frames, or there for the first time: clear what ANTIC is
; about to read, as the title program does once when it starts. Its first
; frame then appears in its own way.
to_title:
        lda #0
        sta frame_ready         ; the kernel's handler, if it is on: black
        sta DMACTL
        tay
        ldx #>BITMAP
@page:  stx @byte+2
@byte:  sta BITMAP,y
        iny
        bne @byte
        inx
        cpx #$FF
        bne @page
:       sta $FF00,y
        iny
        cpy #$40
        bne :-
        ldy #0
        ldx #>BUFFER
@pages: stx @copy+2
@copy:  sta BUFFER,y
        iny
        bne @copy
        inx
        cpx #>BUFFER + 8
        bne @pages
        lda #>title_nmi
        sta NMI_VECTOR+1
        lda #0
        sta stage
        sta fresh
        lda #1
        sta frame_ready
        jmp leave

; --- the scenes with two pictures in a frame --------------------------------
; Scenes 3, 5, 7 and 9 put two pictures side by side, each in two colours of
; its own, inside a frame of a fifth colour, with white text below. A C64 cell
; has its own colours; an Atari row has two besides black and white. The
; kernel's screen copy takes each row's two commonest colours, counting what
; the colour matrix names in every cell, used or not. Here that loses the
; frame in some rows and changes colours from row to row.
;
; So before the copy the colour matrix at $CC00 is prepared: wherever a cell
; does not draw one of its two colours, that colour is replaced by the frame's
; or, in the rows of the pictures, by the commonest other colour drawn in
; them. Nothing on a C64 screen would change. The copy then finds the frame's
; colour and that one in every row of the pictures, and the frame's and the
; text's shade below. The title program writes the matrix again from its own
; copy with every scene.
SCENE        = $4938            ; the title program's count: even after these scenes
MATRIX       = $CC00
cell    = $F0                   ; kept and put back, as the screen copy does
colours = $F2
PICTURE_FIRST = 1               ; the rows of the two pictures
PICTURE_END   = 14

portraits:
        lda SCENE
        lsr a
        bcc :+
        rts
:       ldx #3
:       lda cell,x
        sta kept_zp,x
        dex
        bpl :-
        ldx #15
        lda #0
:       sta drawn,x
        dex
        bpl :-
        sta first
        sta second
        lda MATRIX              ; the frame: the first cell, drawn in one colour
        tax
        lda BITMAP
        jsr pairs
        txa
        ldy first
        beq :+
        lsr a
        lsr a
        lsr a
        lsr a
:       and #$0F
        sta frame
        asl a
        asl a
        asl a
        asl a
        sta frame_high
        lda #0                  ; first pass: count the colours drawn in the pictures
        sta rewrite
        lda #PICTURE_FIRST
        ldx #PICTURE_END
        jsr walk
        ldx #15                 ; the commonest that is not the frame's
        lda frame
        sta other
        lda #0
        sta most
:       cpx frame
        beq :+
        lda drawn,x
        cmp most
        bcc :+
        beq :+
        sta most
        stx other
:       dex
        bne :--
        inc rewrite             ; second pass: all rows
        lda #0
        ldx #25
        jsr walk
        ldx #3
:       lda kept_zp,x
        sta cell,x
        dex
        bpl :-
        rts

; Rows A to X - 1: for every cell find which of its two colours it draws, then
; count them or rewrite its matrix byte.
walk:   sta walk_row
        stx last
        tax                     ; cell = BITMAP + 320 row, colours = MATRIX + 40 row
        lda #<BITMAP
        sta cell
        lda #>BITMAP
        sta cell+1
        lda #<MATRIX
        sta colours
        lda #>MATRIX
        sta colours+1
        txa
        beq @row
:       clc
        lda cell
        adc #<320
        sta cell
        lda cell+1
        adc #>320
        sta cell+1
        clc
        lda colours
        adc #40
        sta colours
        bcc :+
        inc colours+1
:       dex
        bne :--
@row:   lda frame               ; what an unused low nibble becomes in this row
        ldx walk_row
        cpx #PICTURE_FIRST
        bcc :+
        cpx #PICTURE_END
        bcs :+
        lda other
:       sta low
        lda #40
        sta count_cells
@cell:  lda #0
        sta first
        sta second
        ldy #7
@byte:  lda (cell),y
        beq :+
        jsr pairs
:       dey
        bpl @byte
        ldy #0
        lda (colours),y
        ldx rewrite
        bne @change
        pha                     ; count the colours this cell draws
        lsr a
        lsr a
        lsr a
        lsr a
        tax
        lda first
        beq :+
        inc drawn,x
        bne :+
        dec drawn,x
:       pla
        and #$0F
        tax
        lda second
        beq @next
        inc drawn,x
        bne @next
        dec drawn,x
        bne @next
@change:
        ldx first
        bne :+
        and #$0F
        ora frame_high
:       ldx second
        bne :+
        and #$F0
        ora low
:       sta (colours),y
@next:  clc
        lda cell
        adc #8
        sta cell
        bcc :+
        inc cell+1
:       inc colours
        bne :+
        inc colours+1
:       dec count_cells
        bne @cell
        inc walk_row
        lda walk_row
        cmp last
        beq :+
        jmp @row
:       rts

; Which pixel pairs byte A has: `first` gets a bit for every pair 01 (the
; matrix byte's high nibble), `second` for every pair 10 (its low nibble).
pairs:  sta t_target
        lsr a
        eor #$FF
        and t_target
        and #$55
        ora first
        sta first
        lda t_target
        asl a
        eor #$FF
        and t_target
        and #$AA
        ora second
        sta second
        rts

; --- the tune --------------------------------------------------------------
; The title program's interrupt handler plays three SID voices from tables:
; frequency, length in ticks and gate for each note. Its writes land in the
; kernel's stand-in registers. Each frame they are turned into POKEY's:
; voice 1 on the joined channels 1+2, as the game's effects, voices 2 and 3 on
; channels 3 and 4. Pitches come from a table of the frequencies the tune
; uses (title-music.inc); the envelope is the kernel's linear one.
music:  lda fake_sid+$18
        and #$0F
        sta master
        ldx #2
@voice: stx voice
        ldy sid_voice,x
        sty sid
        lda master
        beq @mute
        lda fake_sid+4,y
        and #$70                ; triangle, saw or pulse
        beq @mute
        ldx #TITLE_NOTES-1
@find:  lda fake_sid,y
        cmp note_low,x
        bne :+
        lda fake_sid+1,y
        cmp note_high,x
        beq @found
:       dex
        bpl @find
@mute:  ldx voice               ; silent, a rest or not a pitch of the tune
        lda #0
        sta level,x
        sta gate,x
        sta phase,x
        jmp @volume
@found: lda voice
        bne :+
        lda note_wide_low,x
        sta AUDF1
        lda note_wide_high,x
        jmp @pitch
:       lda note_narrow,x
@pitch: ldx voice
        ldy pokey_voice,x
        sta AUDF1-1,y
        ldy sid
        lda fake_sid+4,y
        and #1
        cmp gate,x
        beq :+
        sta gate,x
        sta phase,x             ; a rising gate attacks, a falling one releases
:       lda phase,x
        cmp #1
        bne @fall
        lda fake_sid+5,y
        lsr a
        lsr a
        lsr a
        lsr a
        tay
        lda level,x
        clc
        adc sound_attack_step,y
        bcs :+
        cmp #$F0
        bcc @store
:       lda #2
        sta phase,x
        lda #$F0
        bne @store
@fall:  lda phase,x
        beq @release
        lda fake_sid+6,y
        and #$F0
        sta t_target            ; decay ends at the sustain level
        lda fake_sid+5,y        ; and its speed is in attack/decay
        jmp @rate
@release:
        sta t_target            ; release ends at zero
        lda fake_sid+6,y        ; and its speed is in sustain/release
@rate:  and #$0F
        tay
        lda level,x
        sec
        sbc sound_release_step,y
        bcc :+
        cmp t_target
        bcs @store
:       lda t_target
@store: sta level,x
@volume:
        lda level,x
        lsr a
        lsr a
        lsr a
        lsr a
        cmp master
        bcc :+
        lda master
:       sta t_target            ; three voices: three quarters of each
        lsr a
        lsr a
        eor #$FF
        sec
        adc t_target
        ora #$A0                ; pure tone
        ldy pokey_voice,x
        sta AUDC1-1,y
        dex
        bmi :+
        jmp @voice
:       rts
sid_voice:      .byte 0, 7, 14
pokey_voice:    .byte 3, 5, 7   ; AUDC2, AUDC3, AUDC4; the AUDF is one below
        .include "title-music.inc"

; --- the machine routines the title program calls ---------------------------
; GETIN. The title program calls it only when the keyboard buffer has a key.
; Escape ($5F, the C64's left arrow) starts the game: the title program would
; load the game's first files itself; the boot code does that instead, and
; sets memory as the title program leaves it.
title_getin:
        php
        sei                     ; the keyboard routine fills the buffer
        lda KEY_COUNT
        beq @none
        ldy KEY_BUFFER
        ldx #0
:       lda KEY_BUFFER+1,x
        sta KEY_BUFFER,x
        inx
        cpx #9
        bne :-
        dec KEY_COUNT
        cpy #$5F
        bne :+
        jmp leave_title
:       tya
@none:  plp
        cmp #0
        rts

; The disk read. The title program starts by loading three of the game's
; tables ($8C00, $C92C, $C9E8) that it does not use itself. The boot code
; loads them with the rest of the game, so here they are passed over.
title_read:
        lda param_address+1
        bmi :+
        jmp disk_read
:       lda param_address       ; return as the read does
        sta $FC
        clc
        lda param_address+1
        adc param_length+1
        sta $FD
        lda #0
        sta $FE
        sta $FF
        ldy param_length
        ldx x_after
        lda #0
        cmp #0
        rts

; --- in and out --------------------------------------------------------------
start:  sei
        cld
        lda #0
        sta NMIEN
        sta DMACTL
        sta DISPLAY_MODE        ; the screen copy looks here for the encounter layout
        sta KEY_COUNT
        sta KEY_REPEAT
        sta side
        sta busy
        sta fresh
        sta next
        sta passes
        ldx #2
:       sta level,x
        sta gate,x
        sta phase,x
        dex
        bpl :-
        ldx #31
:       sta fake_sid,x
        dex
        bpl :-
        lda #1
        sta stage               ; nothing to show yet
        sta shown_mode          ; the screen is off during disk transfers
        lda #<title_getin
        sta GETIN_JUMP+1
        lda #>title_getin
        sta GETIN_JUMP+2
        lda #<title_read
        sta READ_JUMP+1
        lda #>title_read
        sta READ_JUMP+2
        lda #<tick
        sta IRQ_VECTOR
        lda #>tick
        sta IRQ_VECTOR+1
        lda #>title_nmi
        sta NMI_VECTOR+1
        ldx #6                  ; the title program: side A, block 0
:       lda program,x
        sta param_address,x
        dex
        bpl :-
        jsr disk_read
        lda #$40
        sta NMIEN
        ldx #TITLE_S            ; registers as the C64's loader leaves them
        txs
        lda #TITLE_P
        pha
        lda #TITLE_A
        ldx #TITLE_X
        ldy #TITLE_Y
        plp
        jmp TITLE_START
program:
        .word TITLE_START, TITLE_LENGTH
        .byte 0
        .word 0

; Escape: undo everything above, so that the kernel and the machine are as
; the boot code left them, put the boot code back and let it go on.
leave_title:
        ldx #$FF
        txs
        lda #0
        sta NMIEN
        sta DMACTL
        lda #>nmi
        sta NMI_VECTOR+1
        lda #<getin
        sta GETIN_JUMP+1
        lda #>getin
        sta GETIN_JUMP+2
        lda #<disk_read
        sta READ_JUMP+1
        lda #>disk_read
        sta READ_JUMP+2
        lda #<irq_tail
        sta IRQ_VECTOR
        lda #>irq_tail
        sta IRQ_VECTOR+1
        lda #PB_GAME
        sta PORTB
        jsr sound_restore
        lda #0
        sta shown_mode
        sta KEY_COUNT
        ldx #sound_attack_step - fake_vic - 1          ; the stand-in registers
:       sta fake_vic,x
        dex
        bpl :-
        lda #$13
        sta x_after             ; the video bank byte, as the kernel starts with
        lda #PB_GAME_EXT        ; the text screen the kernel shows next: blank
        sta PORTB
        lda #$20
        ldy #0
:       sta PICTURE,y
        sta PICTURE+$100,y
        sta PICTURE+$200,y
        sta PICTURE+$300,y
        iny
        bne :-
        lda #PB_GAME
        sta PORTB
        lda #1
        sta frame_ready
        ldx #PARK_PAGES         ; the boot code, back where it runs
@page:
@from = * + 2
:       lda PARK,y
@to = * + 2
        sta PARKED,y
        iny
        bne :-
        inc @from
        inc @to
        dex
        bne @page
        lda #$40
        sta NMIEN
        jmp (resume)

; --- variables ----------------------------------------------------------------
stage:  .byte 1
busy:   .byte 0
fresh:  .byte 0                 ; the scene on screen is the one last drawn
t_row:    .byte 0
next:   .byte 0
passes: .byte 0                 ; frames of copying still owed to the last drawing
master: .byte 0
voice:  .byte 0
sid:    .byte 0
t_target: .byte 0
frame:  .byte 0                 ; portraits: the frame's colour
frame_high: .byte 0
other:  .byte 0                 ; the commonest other colour of the pictures
most:   .byte 0
low:    .byte 0
first:  .byte 0
second: .byte 0
rewrite: .byte 0
last:   .byte 0
walk_row: .byte 0
count_cells: .byte 0
kept_zp: .res 4
drawn:  .res 16
level:  .res 3                  ; 0..240; the high nibble is the volume
gate:   .res 3
phase:  .res 3                  ; 1 attack, 2 decay and sustain, 0 release
