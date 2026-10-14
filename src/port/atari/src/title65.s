; Temporary startup stage for the 64 KB Atari. The original C64 title
; program and artwork run before the game's resident files are loaded.
; Animated frames display the raw bitmap directly. Eight later scenes use
; packed colour-role plans and a 256-byte nibble converter in temporary RAM.
; Three original SID voices are translated to POKEY only during this stage.
;
; RAM lifetimes: C64 program $4000-$4F7F; converted scene $5000-$73FF;
; this stage at $8000; parked boot $A000-$BBFF. The crossing-row buffer at
; $1400-$1BFF becomes a 600-byte scene plan while scenes are shown.
; Game loading discards all temporary code, pictures, plans and music tables.
; No extra bank or permanent gameplay allocation. See docs/65XE.md.

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
PB_GAME     = $FE
PB_GAME_EXT = $FE

KEY_COUNT    = $C6
KEY_BUFFER   = $0277
KEY_REPEAT   = $028A
IRQ_VECTOR   = $0314
DISPLAY_MODE = $0389
NMI_VECTOR   = $FFFA
GETIN_JUMP   = $FFE4            ; the kernel's JMP getin
READ_JUMP    = $9D0D            ; the kernel's JMP disk_read
PICTURE      = $5000            ; temporary converted scene
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
        .word title_codes + (.ident(.sprintf("at%d", r)) .mod 1024) / 8
        .endrepeat
        .byte $41
        .word list
list_end:
        .assert >list = >(list_end - 1), error, "the display list crosses a page"
title_codes:  .repeat 128, i
        .byte i
        .endrepeat
chbase: .repeat 25, r
        .byte >.ident(.sprintf("at%d", r)) & $FC
        .endrepeat

scene_list:
        .byte $70,$70
        .repeat 25, r
        .byte $44 | ($80 * (r < 24))
        .if r < 16
        .word scene_panel + (r .mod 3)*40
        .else
        .word title_codes + (r .mod 3)*40
        .endif
        .endrepeat
        .byte $41
        .word scene_list
scene_panel:
        .repeat 120, i
        .byte i | ($80 * ((i .mod 40) >= 30))
        .endrepeat
scene_chbase:
        .repeat 25, r
        .byte >(PICTURE+(r/3)*1024)
        .endrepeat
PLAN = $1400

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
        lda row_chbase,x
        sta WSYNC
        sta CHBASE
        lda active_pf0,x
        sta COLPF0
        lda active_pf1,x
        sta COLPF1
        lda active_pf2,x
        sta COLPF2
        lda active_pf3,x
        sta COLPF3
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
        lda stage
        cmp #2
        beq @scene
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
        jmp @ready
@scene: lda #<scene_list
        sta DLISTL
        lda #>scene_list
        sta DLISTH
        lda scene_chbase
        sta CHBASE
        lda active_pf0
        sta COLPF0
        lda active_pf1
        sta COLPF1
        lda active_pf2
        sta COLPF2
        lda active_pf3
        sta COLPF3
@ready:
        lda #0
        sta COLBK
        lda #1
        sta t_row
        lda #$C0
        ldx #$22
        ldy busy
        bne @blank
        ldy stage
        cpy #1
        bne :+
@blank:
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
        lda title_copy_low,x
        sta @go+1
        lda title_copy_high,x
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
title_copy_low:   .lobytes copy0, copy1, copy2, copy3, copy4, copy5
title_copy_high:  .hibytes copy0, copy1, copy2, copy3, copy4, copy5

; --- once a frame, after the title program's own interrupt handler ---------
; Reached through $0314 as the KERNAL's handler is on the C64, so only while
; the title program has interrupts enabled. stage: 0 the title frames are
; shown; 1 black, waiting for the first scene; 2 a converted scene is shown.
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
        jsr scene_convert
        ldx #24
:       lda scene_chbase,x
        sta row_chbase,x
        lda PLAN,x
        sta active_pf0,x
        lda PLAN+25,x
        sta active_pf1,x
        lda PLAN+50,x
        sta active_pf2,x
        lda PLAN+75,x
        sta active_pf3,x
        dex
        bpl :-
        sei
        lda SCENE
        sta rendered_scene
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
        ldx #24
:       lda chbase,x
        sta row_chbase,x
        lda #TITLE_PF0
        sta active_pf0,x
        lda #TITLE_PF1
        sta active_pf1,x
        lda #TITLE_PF2
        sta active_pf2,x
        sta active_pf3,x
        dex
        bpl :-
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
        sta rendered_scene
        lda #1
        sta frame_ready
        jmp leave

; Scene plans contain 100 row palette bytes and 500 packed cell mappings.
; Decode two pixel pairs at a time with a 256-byte table, while the original
; bitmap and colour metadata stay untouched. Temporary output is $5000-$73FF.
SCENE = $4938
source65 = $F0
output65 = $F2
plan65 = $F4
scene_convert:
        ldx #5
:       lda $F0,x
        sta kept_zp,x
        dex
        bpl :-
        lda #0
        sta param_address
        sta param_offset
        lda #>PLAN
        sta param_address+1
        lda #<600
        sta param_length
        lda #>600
        sta param_length+1
        lda SCENE
        sec
        sbc #3
        asl a
        tax
        lda plan_blocks,x
        sta param_block
        lda plan_blocks+1,x
        sta param_block+1
        lda #TITLE_PLAN_SIDE
        sta side
        jsr disk_read
        lda #0
        sta side
        sta source65
        sta output65
        sta render_row
        lda #>BITMAP
        sta source65+1
        lda #>PICTURE
        sta output65+1
        lda #<(PLAN+100)
        sta plan65
        lda #>(PLAN+100)
        sta plan65+1
@row:   lda #20
        sta render_pairs
@pair:  ldy #0
        lda (plan65),y
        pha
        and #15
        asl a
        asl a
        asl a
        asl a
        sta render_mapping
        jsr render_cell
        pla
        and #$F0
        sta render_mapping
        jsr render_cell
        inc plan65
        bne :+
        inc plan65+1
:       dec render_pairs
        bne @pair
        inc render_row
        lda render_row
        cmp #25
        beq @done
        ; A converted 320-byte row leaves 64 unused bytes every third row.
        ldx render_row
        lda render_offset,x
        beq @row
        clc
        adc output65
        sta output65
        bcc @row
        inc output65+1
        bne @row
@done:  ldx #5
:       lda kept_zp,x
        sta $F0,x
        dex
        bpl :-
        rts
render_cell:
        ldy #7
@byte:  lda (source65),y
        pha
        and #15
        ora render_mapping
        tax
        lda nibble_map,x
        sta render_low
        pla
        lsr a
        lsr a
        lsr a
        lsr a
        ora render_mapping
        tax
        lda nibble_map,x
        asl a
        asl a
        asl a
        asl a
        ora render_low
        sta (output65),y
        dey
        bpl @byte
        clc
        lda source65
        adc #8
        sta source65
        bcc :+
        inc source65+1
:       clc
        lda output65
        adc #8
        sta output65
        bcc :+
        inc output65+1
:       rts
render_offset:
        .repeat 25,r
        .byte $40 * ((r > 0) .and ((r .mod 3) = 0))
        .endrepeat
        .include "title65-plans.inc"
nibble_map:
        .incbin "title65-nibbles.bin"
        .include "sound-envelope.inc"

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
        lda #$FF
        sta shown_mode          ; next text publication must rebuild the OS font
        lda #0
        sta frame_ready
        sta KEY_COUNT
        ; Preserve the live code/CHBASE in reserved stand-in VIC bytes.
        ldx #$21
:       sta fake_vic,x
        dex
        cpx #$10
        bne :-
        lda #$13
        sta x_after
        ldy #0
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
rendered_scene: .byte 0         ; original scene counter committed by conversion
t_row:    .byte 0
next:   .byte 0
passes: .byte 0                 ; frames of copying still owed to the last drawing
master: .byte 0
voice:  .byte 0
sid:    .byte 0
t_target: .byte 0
kept_zp: .res 6
level:  .res 3                  ; 0..240; the high nibble is the volume
gate:   .res 3
phase:  .res 3                  ; 1 attack, 2 decay and sustain, 0 release

render_row: .byte 0
render_pairs: .byte 0
render_mapping: .byte 0
render_low: .byte 0

active_pf0: .res 25
active_pf1: .res 25
active_pf2: .res 25
active_pf3: .res 25
