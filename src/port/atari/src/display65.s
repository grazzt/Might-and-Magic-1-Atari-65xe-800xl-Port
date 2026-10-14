; Direct display: nineteen native rows and six copies. No extended RAM.
; The colour matrices are presentation storage after their writers are patched.
        .segment "UNDER"
display_start:
list65_start:
bitmap_list:
        .byte $70, $70
        cursor .set -1
        .repeat 25, r
        .if (r = 3) .or (r = 12)
        offset .set 0
        .elseif (r = 6) .or (r = 19)
        offset .set 40
        .elseif (r = 9) .or (r = 22)
        offset .set 80
        .else
        offset .set ((r*320) .mod 1024)/8
        .endif
        .if offset = cursor
        .byte $04 | ($80 * (r < 24))
        .else
        .byte $44 | ($80 * (r < 24))
        .word codes+offset
        .endif
        cursor .set offset+40
        .endrepeat
        .byte $41
        .word bitmap_list
list65_end:
codes:
        .repeat 128, i
        .byte i
        .endrepeat
        .segment "PLAY65"
play65_start:
; The original colour fill leaves these exact registers, pointers and NZVC.
; There is no SED in any traced game module; binary ADC sets V as before.
        clc
        lda #$58
        adc #$28
        sta $4D
        lda #$DA
        sta $4E
        lda #$0C
        ldx #0
        ldy #0
        rts
native_base:
        .repeat 25, r
        .if r = 3 || r = 6 || r = 9
        .byte $CC
        .elseif r = 12 || r = 19 || r = 22
        .byte $D8
        .else
        .byte >($E000+r*320) & $FC
        .endif
        .endrepeat
font_if_needed:
        lda shown_mode
        beq :+
        jsr make_font
:       rts
font_error:
        inc font_failed
        jmp font_done
play65_end:

        .segment "COLOUR65"
colour65_start:
        ldy #0                  ; original fill's only non-colour result
        rts
cross_low:  .lobytes $E3C0,$E780,$EB40,$EF00,$F7C0,$FB80
cross_high: .hibytes $E3C0,$E780,$EB40,$EF00,$F7C0,$FB80
colour65_end:

        .segment "BANK65"
bank65_start:
        sta $C40C               ; keep original bank variable and loader contract
        jmp $C420
copy_low:   .lobytes $CC00,$CD40,$CE80,$D800,$D940,$DA80
copy_high:  .hibytes $CC00,$CD40,$CE80,$D800,$D940,$DA80
        .byte 0
        jsr $9D0A               ; retain the original interior entry at $C420
        rts
bank65_end:

        .segment "UNDER"
refresh65_start:

refresh:
        ldx #3
:       lda $F0,x
        pha
        dex
        bpl :-
        lda IRQ_VECTOR
        cmp #<GAME_IRQ
        bne rf_text
        lda IRQ_VECTOR+1
        cmp #>GAME_IRQ
        bne rf_text
        lda DISPLAY_MODE
        bne rf_bitmap
rf_text:
        jsr rf_blank            ; text/font ownership changes still need blank DMA
        jsr font_if_needed
        ldy #0
:       lda $0400,y
        sta PICTURE,y
        lda $0500,y
        sta PICTURE+$100,y
        lda $0600,y
        sta PICTURE+$200,y
        lda $0700,y
        sta PICTURE+$300,y
        iny
        bne :-
        lda #0
        beq rf_publish
rf_bitmap:
        sta mode
        lda shown_mode
        beq rf_bitmap_blank
        bmi rf_bitmap_blank     ; initial $FF has no completed visible frame
        lda #$80
        sta frame_ready         ; keep DMA/DLIs; bit zero holds the game clock
        bne rf_bitmap_copy
rf_bitmap_blank:
        jsr rf_blank
rf_bitmap_copy:
        ldx #5
rf_cross:
        lda cross_low,x
        sta source
        lda cross_high,x
        cpx #4
        bcs :+
        ldy mode
        cpy #2
        bne :+
        sec
        sbc #$C0
:       sta source+1
        lda copy_low,x
        sta dest
        lda copy_high,x
        sta dest+1
        ldy #0
:       lda (source),y
        sta (dest),y
        iny
        bne :-
        inc source+1
        inc dest+1
:       lda (source),y
        sta (dest),y
        iny
        cpy #64
        bne :-
        dex
        bpl rf_cross
        ldx #24
:       lda native_base,x
        cpx #16
        bcs :+
        cmp #$E0                ; crossing slots stay at $CC/$D8 in either mode
        bcc :+
        ldy mode
        cpy #2
        bne :+
        sec
        sbc #$C0
:       sta row_chbase,x
        dex
        bpl :--
        lda mode
rf_publish:
        sta shown_mode
        ldx #0
:       pla
        sta $F0,x
        inx
        cpx #4
        bne :-
        inc frame_ready
        rts
display_end:

; Force one publication per high-level wait/pause, even if the faster direct
; renderer reaches it within two frames. Ordinary idle polls retain the old
; heuristic, so they neither recopy the screen nor hold the clock repeatedly.
; The second, unreferenced copy of the Y/N reader supplies this resident space.
        .segment "WAIT65"
        jmp wait65
        nop
        .segment "PAUSE65"
        jmp pause65
        .segment "DELAY65"
        jmp pause65
        .segment "WAITSPY65"
wait65:
        inc key_given
        lda #0
        sta KEY_COUNT
        jmp $0E3B
pause65:
        inc key_given
        jmp $C355               ; LDX #0 overwrites INC's NZ, preserving A/C/V

        .segment "FLIP65"
        jmp mode65
        nop
        nop
        .segment "COPYCOLOUR65"
; The omitted colour copy's final A is $05AA; X, pointers and carry survive,
; Y=0 sets NZ exactly as the old final DEY. No bitmap bytes are omitted.
        lda $05AA
        ldy #0
        rts
mode65:
        sta DISPLAY_MODE
        php
        pha
        txa
        pha
        tya
        pha
        jsr refresh
        jmp mode_resume
